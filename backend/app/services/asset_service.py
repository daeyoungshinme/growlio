from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Position, Transaction
from app.providers.base import BrokerProvider
from app.providers.kis_provider import KISProvider
from app.providers.kiwoom_provider import KiwoomProvider
from app.providers.manual_provider import ManualProvider
from app.providers.openbanking_provider import OpenBankingProvider
from app.utils.currency import fetch_usd_krw

logger = structlog.get_logger()

_PROVIDERS: dict[str, BrokerProvider] = {
    "KIS_API": KISProvider(),
    "KIWOOM_API": KiwoomProvider(),
    "OPEN_BANKING": OpenBankingProvider(),
    "MANUAL": ManualProvider(),
}


async def sync_account(account: AssetAccount, db: AsyncSession, redis: Any) -> AssetSnapshot:
    """모든 데이터 소스를 통합 처리하는 계좌 동기화 진입점.

    SyncError 계층 예외를 그대로 전파한다. API 레이어에서 HTTPException으로 변환.
    """
    from app.exceptions import ProviderCredentialError

    provider = _PROVIDERS.get(account.data_source)
    if provider is None:
        raise ProviderCredentialError(f"지원하지 않는 데이터 소스: {account.data_source}")
    balance = await provider.sync(account, db, redis)

    if balance.deposit_krw:
        account.deposit_krw = balance.deposit_krw
    if balance.deposit_foreign:
        account.deposit_usd = balance.deposit_foreign

    if balance.positions:
        # 계좌 현재 포지션 교체 (snapshot_id IS NULL)
        await db.execute(
            delete(Position).where(Position.account_id == account.id, Position.snapshot_id == None)  # noqa: E711
        )
        for p in balance.positions:
            db.add(Position(
                account_id=account.id,
                snapshot_id=None,
                ticker=p.ticker, name=p.name, market=p.market,
                qty=p.qty, avg_price=p.avg_price, avg_price_usd=p.avg_price_usd,
                current_price=p.current_price,
                value_krw=p.value_krw,
                currency=p.currency, usd_rate=p.usd_rate,
            ))
    await db.commit()

    today = balance.extra.get("snapshot_date", date.today())
    source = balance.extra.get("source", account.data_source)

    snapshot = await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=today,
        amount_krw=balance.total_value_krw,
        invested_amount=balance.invested_krw or None,
        unrealized_pnl=balance.pnl_krw or None,
        usd_krw_rate=balance.usd_krw_rate if balance.usd_krw_rate != 1300.0 else None,
        source=source,
    )

    # 스냅샷 포지션 저장 (기존 snapshot의 포지션 교체)
    if balance.positions:
        await db.execute(
            delete(Position).where(Position.snapshot_id == snapshot.id)
        )
        for p in balance.positions:
            db.add(Position(
                account_id=account.id,
                snapshot_id=snapshot.id,
                ticker=p.ticker, name=p.name, market=p.market,
                qty=p.qty, avg_price=p.avg_price, avg_price_usd=p.avg_price_usd,
                current_price=p.current_price,
                value_krw=p.value_krw,
                currency=p.currency, usd_rate=p.usd_rate,
            ))
        await db.commit()

    logger.info("account_synced", account_id=str(account.id), source=source, total_krw=balance.total_value_krw)
    return snapshot


_STOCK_TYPES = {"STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER"}


def _eval_value(pos_list: list) -> float:
    return sum(float(p.current_price or p.avg_price or 0) * float(p.qty or 0) for p in pos_list)


def _invested_value(pos_list: list) -> float:
    return sum(float(p.avg_price or 0) * float(p.qty or 0) for p in pos_list)


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

    # 스냅샷 ID → Position 목록 사전 로드 (쿼리 최소화)
    snap_ids = [snap.id for snap, acc in rows if acc.asset_type in _STOCK_TYPES]
    snap_positions: dict[Any, list] = {}
    if snap_ids:
        pos_result = await db.execute(
            select(Position).where(Position.snapshot_id.in_(snap_ids))
        )
        for pos in pos_result.scalars().all():
            snap_positions.setdefault(pos.snapshot_id, []).append(pos)

    # 계좌 ID → 현재 Position 목록 사전 로드
    stock_acc_ids = [acc.id for _, acc in rows if acc.asset_type in _STOCK_TYPES]
    stock_acc_ids += [acc.id for acc in no_snap_accounts if acc.asset_type in _STOCK_TYPES]
    current_positions: dict[Any, list] = {}
    if stock_acc_ids:
        cur_result = await db.execute(
            select(Position).where(
                Position.account_id.in_(stock_acc_ids),
                Position.snapshot_id == None,  # noqa: E711
            )
        )
        for pos in cur_result.scalars().all():
            current_positions.setdefault(pos.account_id, []).append(pos)

    for snap, acc in rows:
        if not acc.include_in_total:
            continue
        if acc.asset_type in _STOCK_TYPES:
            pos_list = snap_positions.get(snap.id) or current_positions.get(acc.id) or []
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
            pos_list = current_positions.get(acc.id) or []
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

    xirr_pct = await _calc_xirr(user_id, total_assets_krw, db)

    from sqlalchemy import func as sqlfunc
    first_snap_result = await db.execute(
        select(sqlfunc.min(AssetSnapshot.snapshot_date)).where(AssetSnapshot.user_id == user_id)
    )
    first_snap_date = first_snap_result.scalar()
    benchmarks = await _get_benchmarks(first_snap_date, redis) if first_snap_date else {"kospi_pct": None, "sp500_pct": None}

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
        "xirr_pct": xirr_pct,
        "benchmark_kospi_pct": benchmarks.get("kospi_pct"),
        "benchmark_sp500_pct": benchmarks.get("sp500_pct"),
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


def _xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """Newton-Raphson XIRR. cashflows: [(date, amount)] 음수=유출, 양수=유입."""
    if len(cashflows) < 2:
        return None
    amounts = [a for _, a in cashflows]
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    d0 = min(d for d, _ in cashflows)
    days = [(d - d0).days for d, _ in cashflows]

    pairs = list(zip(amounts, days, strict=True))
    rate = 0.1
    for _ in range(200):
        try:
            npv = sum(cf / (1 + rate) ** (d / 365.0) for cf, d in pairs)
            dnpv = sum(
                -cf * (d / 365.0) / (1 + rate) ** (d / 365.0 + 1) for cf, d in pairs
            )
        except (ZeroDivisionError, OverflowError):
            return None
        if abs(dnpv) < 1e-12:
            break
        new_rate = rate - npv / dnpv
        if abs(new_rate - rate) < 1e-7:
            return round(new_rate * 100, 2)
        rate = max(new_rate, -0.99)
    return None


async def _calc_xirr(user_id: uuid.UUID, current_total: float, db: AsyncSession) -> float | None:
    """Transaction 기반 XIRR 계산. 트랜잭션 없으면 None."""
    from sqlalchemy import asc

    result = await db.execute(
        select(Transaction.transaction_date, Transaction.transaction_type, Transaction.amount)
        .where(
            Transaction.user_id == user_id,
            Transaction.transaction_type.in_(["DEPOSIT", "WITHDRAWAL"]),
        )
        .order_by(asc(Transaction.transaction_date))
    )
    rows = result.all()
    if not rows:
        return None

    cashflows: list[tuple[date, float]] = []
    for row in rows:
        if row.transaction_type == "DEPOSIT":
            cashflows.append((row.transaction_date, -float(row.amount)))
        else:
            cashflows.append((row.transaction_date, float(row.amount)))

    cashflows.append((date.today(), current_total))
    return _xirr(cashflows)


async def _get_benchmarks(start_date: date, redis) -> dict[str, float | None]:
    """KOSPI·S&P500의 start_date~오늘 수익률 조회. Redis 24h 캐시."""
    end_date = date.today()
    cache_key = f"benchmark:{start_date}:{end_date}"

    if redis:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    def _fetch() -> dict[str, float | None]:
        import yfinance as yf  # type: ignore[import-untyped]

        result: dict[str, float | None] = {}
        for symbol, key in [("^KS11", "kospi_pct"), ("^GSPC", "sp500_pct")]:
            try:
                hist = yf.Ticker(symbol).history(
                    start=start_date,
                    end=end_date + timedelta(days=1),
                )
                if len(hist) >= 2:
                    pct = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                    result[key] = round(float(pct), 2)
                else:
                    result[key] = None
            except Exception:
                result[key] = None
        return result

    loop = asyncio.get_running_loop()
    try:
        data = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=15.0)
    except Exception:
        data = {"kospi_pct": None, "sp500_pct": None}

    if redis:
        await redis.set(cache_key, json.dumps(data), ex=86400)

    return data


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
