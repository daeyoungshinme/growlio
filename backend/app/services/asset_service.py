from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.kis.auth import get_access_token
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.kis.client import KisTokenExpiredError
from app.kis.overseas_quote import get_overseas_price
from app.exceptions import BadRequestError, CredentialMissingError
from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.services.credential_service import decrypt
from app.utils.currency import cache_usd_krw_rate, fetch_usd_krw, get_usd_krw_rate

logger = structlog.get_logger()


def _to_manual_position(p: dict, usd_krw_rate: float) -> dict:
    """KIS 잔고 포지션을 manual_positions 형식으로 변환 (모든 가격 KRW)."""
    if p.get("currency") == "USD":
        avg_usd = float(p.get("avg_price", 0))
        cur_usd = float(p.get("current_price", 0))
        return {
            "ticker": p["ticker"], "name": p["name"], "market": p["market"],
            "qty": p["qty"],
            "avg_price": avg_usd * usd_krw_rate,
            "avg_price_usd": avg_usd,
            "usd_rate": usd_krw_rate,
            "current_price": cur_usd * usd_krw_rate,
        }
    return {
        "ticker": p["ticker"], "name": p["name"], "market": p["market"],
        "qty": p["qty"],
        "avg_price": float(p.get("avg_price", 0)),
        "avg_price_usd": None,
        "usd_rate": None,
        "current_price": float(p["current_price"]) if p.get("current_price") else None,
    }


async def sync_kis_account(
    account: AssetAccount,
    db: AsyncSession,
    redis,
) -> AssetSnapshot:
    """KIS 계좌 잔고를 API로 조회해 스냅샷을 저장한다.

    account.kis_app_key/kis_app_secret 필수. 미설정 시 ValueError 발생.
    """
    if not account.kis_app_key or not account.kis_app_secret:
        raise CredentialMissingError("KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요.")
    app_key = decrypt(account.kis_app_key)
    app_secret = decrypt(account.kis_app_secret)
    is_mock = account.is_mock_mode
    token_account_id = str(account.id)
    token_user_id = str(account.user_id)

    logger.info("kis_sync_start", account_no=account.kis_account_no, is_mock=is_mock, has_own_creds=bool(account.kis_app_key))

    access_token = await get_access_token(
        app_key,
        app_secret,
        is_mock=is_mock,
        redis=redis,
        db=db,
        user_id=token_user_id,
        account_id=token_account_id,
    )

    try:
        domestic = await get_domestic_balance(app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock)
        overseas = await get_overseas_balance(app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock)
    except KisTokenExpiredError:
        logger.warning("kis_token_expired_refreshing", account_no=account.kis_account_no, is_mock=is_mock)
        access_token = await get_access_token(
            app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
            user_id=token_user_id, account_id=token_account_id, force_refresh=True,
        )
        domestic = await get_domestic_balance(app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock)
        overseas = await get_overseas_balance(app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock)

    # USD → KRW 환산 (Redis 캐시 우선, API 조회 후 캐시 업데이트)
    usd_krw_rate = await get_usd_krw_rate(redis)
    if overseas["positions"]:
        sample_ticker = overseas["positions"][0]["ticker"]
        sample_market = overseas["positions"][0]["market"]
        try:
            quote = await get_overseas_price(app_key, app_secret, access_token, sample_ticker, sample_market, is_mock=is_mock)
            usd_krw_rate = quote["usd_krw_rate"]
            await cache_usd_krw_rate(redis, usd_krw_rate)
        except Exception as e:
            logger.warning("usd_krw_rate_fetch_failed", ticker=sample_ticker, error=str(e))

    overseas_value_krw = overseas["total_value_usd"] * usd_krw_rate  # 해외 주식 총평가액
    overseas_deposit_krw = overseas["deposit_usd"] * usd_krw_rate   # 외화 예수금 (주식 아님)
    overseas_invested_krw = sum(
        float(p.get("avg_price", 0)) * int(p.get("qty", 0)) * usd_krw_rate
        for p in overseas["positions"]
    )

    stock_value_krw = domestic["total_value_krw"] + overseas_value_krw   # 주식만 (예수금 제외)
    total_value_krw = stock_value_krw + domestic["deposit_krw"] + overseas_deposit_krw  # 전체 자산
    total_invested = domestic["invested_krw"] + overseas_invested_krw    # 국내 + 해외 투자금
    unrealized_pnl = stock_value_krw - total_invested  # 정확한 주식 손익

    all_positions = domestic["positions"] + [
        {**p, "value_krw": p["value_usd"] * usd_krw_rate} for p in overseas["positions"]
    ]

    account.deposit_krw = domestic["deposit_krw"]
    account.deposit_usd = overseas["deposit_usd"]
    account.manual_positions = [_to_manual_position(p, usd_krw_rate) for p in all_positions]
    await db.commit()

    today = date.today()
    snapshot = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=today,
        amount_krw=total_value_krw,
        invested_amount=total_invested,
        unrealized_pnl=unrealized_pnl,
        positions=all_positions,
        usd_krw_rate=usd_krw_rate,
        source="KIS_API",
    )
    logger.info("kis_account_synced", account_id=str(account.id), total_krw=total_value_krw)
    return snapshot


async def sync_kiwoom_account(
    account: AssetAccount,
    db: AsyncSession,
    redis,
) -> AssetSnapshot:
    """키움증권 OpenAPI+ 계좌 잔고를 API로 조회해 스냅샷을 저장한다.

    키움은 전역 자격증명 폴백 없음 — kiwoom_app_key/secret이 없으면 즉시 오류.
    """
    from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
    from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
    from app.kiwoom.client import KiwoomTokenExpiredError

    if not account.kiwoom_app_key or not account.kiwoom_app_secret:
        raise CredentialMissingError("키움 API 자격증명이 설정되지 않았습니다")
    if not account.kiwoom_account_no:
        raise CredentialMissingError("키움 계좌번호가 설정되지 않았습니다")

    app_key = decrypt(account.kiwoom_app_key)
    app_secret = decrypt(account.kiwoom_app_secret)
    is_mock = account.is_mock_mode

    logger.info("kiwoom_sync_start", account_no=account.kiwoom_account_no, is_mock=is_mock)

    async def _do_sync() -> dict:
        token = await kiwoom_get_access_token(
            app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
            user_id=str(account.user_id), account_id=str(account.id),
        )
        try:
            return await kiwoom_get_domestic_balance(
                token, account.kiwoom_account_no, is_mock=is_mock
            )
        except KiwoomTokenExpiredError:
            logger.warning("kiwoom_token_expired_refreshing", account_no=account.kiwoom_account_no)
            refreshed = await kiwoom_get_access_token(
                app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
                user_id=str(account.user_id), account_id=str(account.id), force_refresh=True,
            )
            return await kiwoom_get_domestic_balance(
                refreshed, account.kiwoom_account_no, is_mock=is_mock
            )

    try:
        domestic = await asyncio.wait_for(_do_sync(), timeout=50.0)
    except asyncio.TimeoutError:
        logger.error("kiwoom_sync_timeout", account_no=account.kiwoom_account_no)
        raise RuntimeError("키움 API 응답 시간 초과 (50초). 잠시 후 다시 시도하세요.") from None

    usd_krw_rate = await get_usd_krw_rate(redis)
    total_value_krw = domestic["total_value_krw"] + domestic["deposit_krw"]
    total_invested = domestic["invested_krw"]
    unrealized_pnl = domestic["total_value_krw"] - total_invested

    account.deposit_krw = domestic["deposit_krw"]
    account.manual_positions = [_to_manual_position(p, usd_krw_rate) for p in domestic["positions"]]
    await db.commit()

    snapshot = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=date.today(),
        amount_krw=total_value_krw,
        invested_amount=total_invested,
        unrealized_pnl=unrealized_pnl,
        positions=domestic["positions"],
        usd_krw_rate=usd_krw_rate,
        source="KIWOOM_API",
    )
    logger.info("kiwoom_account_synced", account_id=str(account.id), total_krw=total_value_krw)
    return snapshot


async def sync_openbanking_account(account: AssetAccount, db: AsyncSession) -> AssetSnapshot:
    """오픈뱅킹 계좌 잔액을 조회해 스냅샷을 저장한다."""
    import secrets

    from app.providers.openbanking import ensure_ob_token_fresh, get_account_balance

    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == account.user_id))
    if not settings_row or not settings_row.ob_access_token:
        raise CredentialMissingError("오픈뱅킹 토큰이 없습니다. 다시 연결해주세요.")

    if not account.ob_fintech_use_no:
        raise CredentialMissingError("오픈뱅킹 핀테크이용번호가 없습니다")

    access_token = await ensure_ob_token_fresh(settings_row, db)

    bank_tran_id = f"M{date.today().year:04d}00001U{secrets.token_hex(4).upper()}"
    data = await get_account_balance(
        access_token=access_token,
        fintech_use_no=account.ob_fintech_use_no,
        bank_tran_id=bank_tran_id,
    )

    balance_amt = float(data.get("balance_amt", 0))
    today = date.today()
    snapshot = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=today,
        amount_krw=balance_amt,
        source="OPEN_BANKING",
    )
    logger.info("openbanking_account_synced", account_id=str(account.id), balance=balance_amt)
    return snapshot


async def sync_manual_account(account: AssetAccount, db: AsyncSession, redis=None) -> AssetSnapshot:
    """수동 금액/종목으로 스냅샷을 저장한다. redis가 있으면 현재가도 갱신한다."""
    from app.kis.constants import OVERSEAS_MARKETS

    positions = account.manual_positions or []

    if positions and redis is not None:
        from app.services.price_service import fetch_prices_batch

        tickers = [(p["ticker"], p.get("market", "KOSPI")) for p in positions]
        price_map = await fetch_prices_batch(account.user_id, tickers, db, redis)

        has_overseas = any(p.get("market", "KOSPI") in OVERSEAS_MARKETS for p in positions)
        usd_rate: float | None = None
        if has_overseas:
            usd_rate = await fetch_usd_krw(redis, force_refresh=True) or None

        updated = []
        for p in positions:
            raw_price = price_map.get(p["ticker"])
            if raw_price and p.get("market", "KOSPI") in OVERSEAS_MARKETS and usd_rate:
                price_krw = raw_price * usd_rate
            elif raw_price:
                price_krw = raw_price
            else:
                price_krw = p.get("current_price") or p["avg_price"]
            updated.append({**p, "current_price": price_krw})

        account.manual_positions = updated
        account.manual_updated_at = datetime.now(UTC)
        positions = updated

    invested = _invested_value(positions)
    value = _eval_value(positions)
    pnl = value - invested if positions else 0.0

    if positions:
        usd_rate_val = await fetch_usd_krw(redis)
        deposit = float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate_val
        amount_krw = (value if value else invested) + deposit
        account.manual_amount = amount_krw
    elif account.asset_type == "REAL_ESTATE":
        # 부동산: 순자산(시세 - 담보대출)을 스냅샷에 저장
        gross = float(account.manual_amount or 0)
        mortgage = float((account.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
        amount_krw = gross - mortgage
        if gross == 0:
            raise BadRequestError("부동산 시세(manual_amount)가 설정되지 않았습니다")
    elif account.deposit_krw is not None or account.deposit_usd is not None:
        usd_rate = await fetch_usd_krw(redis)
        amount_krw = float(account.deposit_krw or 0) + float(account.deposit_usd or 0) * usd_rate
    else:
        amount_krw = float(account.manual_amount or 0)
        if amount_krw == 0:
            raise BadRequestError("수동 금액이 설정되지 않았습니다")

    today = date.today()
    snapshot = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=today,
        amount_krw=amount_krw,
        source="MANUAL",
        positions=positions if positions else None,
        invested_amount=invested if invested else None,
        unrealized_pnl=pnl if positions else None,
    )
    return snapshot


_STOCK_TYPES = {"STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER"}


def _eval_value(pos_list: list) -> float:
    return sum((p.get("current_price") or p.get("avg_price", 0)) * p.get("qty", 0) for p in pos_list)


def _invested_value(pos_list: list) -> float:
    return sum(p.get("avg_price", 0) * p.get("qty", 0) for p in pos_list)


async def _build_asset_totals(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis=None,
) -> tuple[float, float, float, dict[str, float]]:
    """최신 스냅샷 기준 총자산·투자금·주식평가액·유형별 금액을 집계한다.
    Returns: (total_assets_krw, total_invested, stock_value, by_type)
    """
    from sqlalchemy import func

    usd_rate = await fetch_usd_krw(redis)

    subq = (
        select(
            AssetSnapshot.account_id,
            func.max(AssetSnapshot.snapshot_date).label("max_date"),
        )
        .where(AssetSnapshot.user_id == user_id)
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    rows = result.all()

    snapped_ids = {acc.id for _, acc in rows}
    from sqlalchemy import and_, or_
    no_snap_result = await db.execute(
        select(AssetAccount).where(
            AssetAccount.user_id == user_id,
            AssetAccount.is_active == True,  # noqa: E712
            or_(
                and_(AssetAccount.manual_amount.isnot(None), AssetAccount.manual_amount > 0),
                AssetAccount.deposit_krw > 0,
                AssetAccount.deposit_usd > 0,
            ),
        )
    )
    no_snap_accounts = [acc for acc in no_snap_result.scalars().all() if acc.id not in snapped_ids]

    total_assets_krw = 0.0
    total_invested = 0.0
    stock_value = 0.0
    by_type: dict[str, float] = {}

    for snap, acc in rows:
        if not acc.include_in_total:
            continue
        if acc.asset_type in _STOCK_TYPES:
            pos_list = snap.positions or acc.manual_positions or []
            amount = float(snap.amount_krw)
            stock_equity = _eval_value(pos_list) if pos_list else amount
            cash = amount - stock_equity
            inv = float(snap.invested_amount or 0) or _invested_value(pos_list)
            stock_value += stock_equity
            total_invested += inv
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + stock_equity
            by_type["CASH_STOCK"] = by_type.get("CASH_STOCK", 0) + cash
        else:
            amount = float(snap.amount_krw)
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        total_assets_krw += amount

    for acc in no_snap_accounts:
        if not acc.include_in_total:
            continue
        if acc.asset_type in _STOCK_TYPES:
            pos_list = acc.manual_positions or []
            pos_equity = _eval_value(pos_list) if pos_list else 0.0
            deposit = float(acc.deposit_krw or 0) + float(acc.deposit_usd or 0) * usd_rate
            computed = pos_equity + deposit
            amount = computed if computed > 0 else float(acc.manual_amount or 0)
            inv = _invested_value(pos_list) if pos_list else float(acc.manual_amount or 0)
            stock_value += pos_equity or amount
            total_invested += inv
            if computed > 0:
                by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + pos_equity
                by_type["CASH_STOCK"] = by_type.get("CASH_STOCK", 0) + deposit
            else:
                by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        elif acc.asset_type == "REAL_ESTATE":
            gross = float(acc.manual_amount or 0)
            mortgage = float((acc.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
            amount = gross - mortgage
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        else:
            amount = float(acc.manual_amount or 0)
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        total_assets_krw += amount

    return total_assets_krw, total_invested, stock_value, by_type


async def get_dashboard_summary(user_id: uuid.UUID, db: AsyncSession, redis=None) -> dict[str, Any]:
    """전체 자산 집계 + 목표 달성률 + 수익률 계산."""
    from app.models.user import UserSettings
    from app.services.dividend_service import get_dividend_summary

    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == user_id))

    total_assets_krw, total_invested, stock_value, by_type = await _build_asset_totals(user_id, db, redis)

    stock_return_pct = ((stock_value / total_invested) - 1) * 100 if total_invested > 0 else 0.0

    goal = float(settings_row.goal_amount) if settings_row and settings_row.goal_amount else None
    goal_pct = (total_assets_krw / goal * 100) if goal else None

    bank_total = total_assets_krw - stock_value
    base = bank_total + total_invested
    annualized_return, cumulative_return = await _calc_returns(user_id, total_assets_krw, base, db)

    monthly_trend = await _get_monthly_trend(user_id, db)

    annual_deposit_goal = float(settings_row.annual_deposit_goal) if settings_row and settings_row.annual_deposit_goal else None
    net_deposits_ytd = await _calc_net_deposits_this_year(user_id, db)
    deposit_achievement_pct = (net_deposits_ytd / annual_deposit_goal * 100) if annual_deposit_goal else None

    div_summary = await get_dividend_summary(user_id, db)

    goal_annual_return_pct = float(settings_row.goal_annual_return_pct) if settings_row and settings_row.goal_annual_return_pct else None
    retirement_target_year = settings_row.retirement_target_year if settings_row else None

    return {
        "total_assets_krw": total_assets_krw,
        "asset_allocation": [
            {"type": k, "amount_krw": v, "pct": v / total_assets_krw * 100 if total_assets_krw else 0}
            for k, v in by_type.items()
        ],
        "goal_amount": goal,
        "goal_achievement_pct": goal_pct,
        "stock_return_pct": stock_return_pct,
        "annual_return_pct": annualized_return,
        "cumulative_return_pct": cumulative_return,
        "goal_annual_return_pct": goal_annual_return_pct,
        "retirement_target_year": retirement_target_year,
        "monthly_trend": monthly_trend,
        "annual_deposit_goal": annual_deposit_goal,
        "deposit_achievement_pct": deposit_achievement_pct,
        "annual_dividends_received": div_summary["annual_received"],
        "estimated_annual_dividends": div_summary["estimated_annual"],
        "dividend_monthly_breakdown": div_summary["monthly_breakdown"],
    }


async def _upsert_snapshot(db: AsyncSession, *, account_id, user_id, snapshot_date, amount_krw, source, **kwargs) -> AssetSnapshot:
    set_values = {"amount_krw": amount_krw, "source": source, **kwargs}
    stmt = (
        pg_insert(AssetSnapshot)
        .values(
            account_id=account_id,
            user_id=user_id,
            snapshot_date=snapshot_date,
            amount_krw=amount_krw,
            source=source,
            **kwargs,
        )
        .on_conflict_do_update(
            constraint="uq_snapshot_account_date",
            set_=set_values,
        )
        .returning(AssetSnapshot)
    )
    result = await db.execute(stmt)
    await db.commit()
    return result.scalar_one()


async def _calc_returns(
    user_id, current_total: float, base: float, db: AsyncSession
) -> tuple[float | None, float | None]:
    """누적수익률 = (현재 총자산 / 기준금액 - 1) × 100
    기준금액 = 통장 금액 + 증권사 총매입금액
    """
    from sqlalchemy import func

    if base <= 0:
        return None, None

    first_snap_result = await db.execute(
        select(func.min(AssetSnapshot.snapshot_date))
        .where(AssetSnapshot.user_id == user_id)
    )
    first_date = first_snap_result.scalar()
    if not first_date:
        return None, None

    today = date.today()
    months = max((today.year - first_date.year) * 12 + (today.month - first_date.month), 1)
    cumulative = (current_total / base - 1) * 100
    annualized = ((current_total / base) ** (12 / months) - 1) * 100
    return annualized, cumulative


async def _get_monthly_trend(user_id, db: AsyncSession) -> list[dict]:
    from sqlalchemy import text

    # 활성 계좌(is_active=TRUE)만 포함, 계좌별 월 최신 스냅샷 1개만 선택 후 합산
    # JOIN으로 비활성 계좌 및 NULL account_id(삭제된 계좌) 스냅샷 자동 제외
    result = await db.execute(
        text("""
            WITH ranked AS (
                SELECT
                    date_trunc('month', s.snapshot_date)::date AS month,
                    s.amount_krw,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.account_id, date_trunc('month', s.snapshot_date)
                        ORDER BY s.snapshot_date DESC
                    ) AS rn
                FROM asset_snapshots s
                JOIN asset_accounts a ON a.id = s.account_id
                WHERE s.user_id = :uid
                    AND a.is_active = TRUE
                    AND a.include_in_total = TRUE
                    AND s.snapshot_date >= (date_trunc('month', CURRENT_DATE) - INTERVAL '11 months')
            )
            SELECT month, SUM(amount_krw) AS total_krw
            FROM ranked
            WHERE rn = 1
            GROUP BY month
            ORDER BY month
        """),
        {"uid": str(user_id)},
    )
    return [{"month": str(row.month), "total_krw": float(row.total_krw)} for row in result]


async def _calc_net_deposits_this_year(user_id, db: AsyncSession) -> float:
    """올해 순입금액 = DEPOSIT 합계 - WITHDRAWAL 합계."""
    from sqlalchemy import func

    year = date.today().year
    result = await db.execute(
        select(
            Transaction.transaction_type,
            func.sum(Transaction.amount).label("total"),
        )
        .where(
            Transaction.user_id == user_id,
            func.extract("year", Transaction.transaction_date) == year,
            Transaction.transaction_type.in_(["DEPOSIT", "WITHDRAWAL"]),
        )
        .group_by(Transaction.transaction_type)
    )
    rows = {r.transaction_type: float(r.total) for r in result}
    return rows.get("DEPOSIT", 0.0) - rows.get("WITHDRAWAL", 0.0)
