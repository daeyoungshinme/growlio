"""포트폴리오 API — 전체 계좌 통합 조회."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.kis.auth import get_access_token
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.limiter import limiter
from app.models.asset import AssetAccount, AssetSnapshot
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.credential_service import decrypt

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

ASSET_TYPE_LABELS: dict[str, str] = {
    "BANK_ACCOUNT": "통장잔고",
    "DEPOSIT": "예금/적금",
    "STOCK_KIS": "주식(KIS)",
    "STOCK_OTHER": "주식(타증권)",
    "CASH_OTHER": "예수금(기타)",
    "OTHER": "기타자산",
    "REAL_ESTATE": "부동산",
}

STOCK_TYPES = {"STOCK_KIS", "STOCK_OTHER"}


@router.get("/overview")
@limiter.limit("10/minute")
async def portfolio_overview(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """모든 계좌 자산을 통합해 포트폴리오 전체 현황을 반환한다."""
    return await _build_portfolio_overview(current_user.id, db)


async def _build_portfolio_overview(user_id, db: AsyncSession) -> dict:
    """포트폴리오 전체 현황 집계 (라우터 및 분석 엔드포인트에서 공용)."""
    # 활성 계좌 전체
    acc_result = await db.execute(
        select(AssetAccount)
        .where(AssetAccount.user_id == user_id, AssetAccount.is_active == True)  # noqa: E712
        .order_by(AssetAccount.sort_order, AssetAccount.created_at)
    )
    accounts: list[AssetAccount] = acc_result.scalars().all()
    if not accounts:
        return _empty_overview()

    # 계좌별 최신 스냅샷
    acc_ids = [a.id for a in accounts]
    subq = (
        select(
            AssetSnapshot.account_id,
            func.max(AssetSnapshot.snapshot_date).label("max_date"),
        )
        .where(AssetSnapshot.account_id.in_(acc_ids))
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )
    snap_result = await db.execute(
        select(AssetSnapshot).join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id)
            & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
    )
    snap_by_acc: dict = {str(s.account_id): s for s in snap_result.scalars().all()}

    # 집계
    total_assets_krw = 0.0
    total_invested_krw = 0.0
    unrealized_pnl_krw = 0.0
    asset_type_totals: dict[str, float] = {}
    all_positions: list[dict] = []
    account_rows: list[dict] = []

    for acc in accounts:
        snap = snap_by_acc.get(str(acc.id))

        # 계좌 금액 결정
        if snap:
            amount_krw = float(snap.amount_krw)
            raw_positions = snap.positions or acc.manual_positions or []
            if snap.invested_amount is not None:
                invested = float(snap.invested_amount)
                pnl = float(snap.unrealized_pnl or 0)
            else:
                invested = sum(p.get("avg_price", 0) * p.get("qty", 0) for p in raw_positions)
                value = sum(
                    (p.get("current_price") or p.get("avg_price", 0)) * p.get("qty", 0)
                    for p in raw_positions
                )
                pnl = value - invested if raw_positions else 0.0
        elif acc.manual_amount is not None:
            if acc.asset_type == "REAL_ESTATE":
                mortgage = float((acc.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
                amount_krw = float(acc.manual_amount) - mortgage
            else:
                amount_krw = float(acc.manual_amount)
            raw_positions = acc.manual_positions or []
            invested = sum(p.get("avg_price", 0) * p.get("qty", 0) for p in raw_positions)
            value = sum(
                (p.get("current_price") or p.get("avg_price", 0)) * p.get("qty", 0)
                for p in raw_positions
            )
            pnl = value - invested if raw_positions else 0.0
        else:
            amount_krw = 0.0
            raw_positions = []
            invested = 0.0
            pnl = 0.0

        if acc.include_in_total:
            total_assets_krw += amount_krw
            asset_type_totals[acc.asset_type] = asset_type_totals.get(acc.asset_type, 0) + amount_krw
        if acc.asset_type in STOCK_TYPES:
            total_invested_krw += invested
            unrealized_pnl_krw += pnl

        # 종목 리스트 (주식 계좌만)
        pos_list: list[dict] = []
        if acc.asset_type in STOCK_TYPES and raw_positions:
            usd_rate = float(snap.usd_krw_rate) if snap and snap.usd_krw_rate else None
            for p in raw_positions:
                qty = int(p.get("qty", 0))
                currency = p.get("currency", "KRW")

                if currency != "KRW" and usd_rate:
                    # 해외주식: USD → KRW 환산 (반올림으로 절삭 오차 최소화)
                    cur_krw = round(float(p.get("current_price") or p.get("avg_price", 0)) * usd_rate)
                    avg_krw = round(float(p.get("avg_price", 0)) * usd_rate)
                    val_amt = round(float(p.get("value_krw") or float(p.get("value_usd", 0)) * usd_rate))
                    inv_amt = avg_krw * qty
                    cur_out = cur_krw
                    avg_out = avg_krw
                else:
                    cur_out = float(p.get("current_price") or p.get("avg_price", 0))
                    avg_out = float(p.get("avg_price", 0))
                    inv_amt = avg_out * qty
                    val_amt = cur_out * qty

                pnl_p = val_amt - inv_amt
                pnl_pct = (pnl_p / inv_amt * 100) if inv_amt else 0.0
                pos_list.append({
                    "ticker": p.get("ticker", ""),
                    "name": p.get("name", ""),
                    "market": p.get("market", "KOSPI"),
                    "qty": qty,
                    "avg_price": avg_out,
                    "current_price": cur_out,
                    "value_krw": val_amt,
                    "invested_krw": inv_amt,
                    "pnl": pnl_p,
                    "pnl_pct": round(pnl_pct, 2),
                    "currency": currency,
                    "account_id": str(acc.id),
                    "account_name": acc.name,
                })
            all_positions.extend(pos_list)

        account_row: dict = {
            "id": str(acc.id),
            "name": acc.name,
            "asset_type": acc.asset_type,
            "asset_type_label": ASSET_TYPE_LABELS.get(acc.asset_type, acc.asset_type),
            "data_source": acc.data_source,
            "institution": acc.institution,
            "amount_krw": amount_krw,
            "invested_krw": invested,
            "unrealized_pnl": pnl,
            "position_count": len(pos_list),
            "positions": pos_list,
            "include_in_total": acc.include_in_total,
        }
        if acc.asset_type == "REAL_ESTATE":
            account_row["real_estate_details"] = acc.real_estate_details
            account_row["market_value_krw"] = float(acc.manual_amount or 0)
        account_rows.append(account_row)

    # 자산 유형별 비율
    asset_type_allocation = [
        {
            "type": t,
            "label": ASSET_TYPE_LABELS.get(t, t),
            "amount_krw": v,
            "pct": round(v / total_assets_krw * 100, 2) if total_assets_krw else 0,
        }
        for t, v in sorted(asset_type_totals.items(), key=lambda x: -x[1])
    ]

    # 종목별 비중 (전체 주식 평가금액 기준, 상위 10 + 기타)
    # 포지션 재집계 대신 계좌 단위 집계값으로 도출 → 요약 카드 3개 값의 수학적 일관성 보장
    stock_total_krw = total_invested_krw + unrealized_pnl_krw
    stock_return_pct = (unrealized_pnl_krw / total_invested_krw * 100) if total_invested_krw else 0.0

    # all_positions에 weight_in_stock 추가
    for p in all_positions:
        p["weight_in_stock"] = round(p["value_krw"] / stock_total_krw * 100, 2) if stock_total_krw else 0

    # 동일 ticker+market을 여러 계좌에 보유한 경우 합산 (차트용)
    ticker_merged: dict[str, dict] = {}
    for p in all_positions:
        key = f"{p['ticker']}-{p['market']}"
        if key not in ticker_merged:
            ticker_merged[key] = {
                "ticker": p["ticker"],
                "name": p["name"],
                "value_krw": 0.0,
                "invested_krw": 0.0,
                "pnl": 0.0,
            }
        ticker_merged[key]["value_krw"] += p["value_krw"]
        ticker_merged[key]["invested_krw"] += p["invested_krw"]
        ticker_merged[key]["pnl"] += p["pnl"]

    sorted_merged = sorted(ticker_merged.values(), key=lambda x: -x["value_krw"])
    top_positions = sorted_merged[:10]
    rest = sorted_merged[10:]
    stock_allocation = [
        {
            "ticker": p["ticker"],
            "name": p["name"],
            "value_krw": p["value_krw"],
            "pct": round(p["value_krw"] / stock_total_krw * 100, 2) if stock_total_krw else 0,
        }
        for p in top_positions
    ]
    if rest:
        stock_allocation.append({
            "ticker": "ETC",
            "name": f"기타 {len(rest)}종목",
            "value_krw": sum(p["value_krw"] for p in rest),
            "pct": round(sum(p["value_krw"] for p in rest) / stock_total_krw * 100, 2) if stock_total_krw else 0,
        })

    return {
        "total_assets_krw": total_assets_krw,
        "total_stock_krw": stock_total_krw,
        "total_non_stock_krw": total_assets_krw - stock_total_krw,
        "total_invested_krw": total_invested_krw,
        "unrealized_pnl_krw": unrealized_pnl_krw,
        "stock_return_pct": round(stock_return_pct, 2),
        "asset_type_allocation": asset_type_allocation,
        "stock_allocation": stock_allocation,
        "all_positions": all_positions,
        "accounts": account_rows,
    }


@router.get("/summary")
async def portfolio_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 등록 계좌 전체 실시간 포트폴리오 집계."""
    import asyncio

    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == current_user.id))
    if not settings_row or not settings_row.kis_app_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="KIS 설정이 필요합니다")

    kis_result = await db.execute(
        select(AssetAccount).where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.data_source == "KIS_API",
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    kis_accounts = kis_result.scalars().all()
    if not kis_accounts:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="등록된 KIS 계좌가 없습니다")

    app_key = decrypt(settings_row.kis_app_key)
    app_secret = decrypt(settings_row.kis_app_secret)
    is_mock = settings_row.kis_is_mock

    redis = await get_redis()
    access_token = await get_access_token(
        app_key, app_secret, is_mock=is_mock, redis=redis, db=db, user_id=str(current_user.id)
    )

    async def _fetch(account_no: str) -> tuple[str, dict, dict]:
        d = await get_domestic_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
        o = await get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
        return account_no, d, o

    results = await asyncio.gather(*[_fetch(acc.kis_account_no) for acc in kis_accounts])

    merged_domestic: dict = {"total_value_krw": 0.0, "invested_krw": 0.0, "pnl_krw": 0.0, "deposit_krw": 0.0, "positions": []}
    merged_overseas: dict = {"total_value_usd": 0.0, "deposit_usd": 0.0, "positions": []}
    account_details = []
    for account_no, d, o in results:
        merged_domestic["total_value_krw"] += d.get("total_value_krw", 0.0)
        merged_domestic["invested_krw"] += d.get("invested_krw", 0.0)
        merged_domestic["pnl_krw"] += d.get("pnl_krw", 0.0)
        merged_domestic["deposit_krw"] += d.get("deposit_krw", 0.0)
        merged_domestic["positions"].extend(d.get("positions", []))
        merged_overseas["total_value_usd"] += o.get("total_value_usd", 0.0)
        merged_overseas["deposit_usd"] += o.get("deposit_usd", 0.0)
        merged_overseas["positions"].extend(o.get("positions", []))
        account_details.append({"account_no": account_no, "domestic": d, "overseas": o})

    stock_return_pct = 0.0
    if merged_domestic["invested_krw"] > 0:
        stock_return_pct = (merged_domestic["total_value_krw"] / merged_domestic["invested_krw"] - 1) * 100

    return {
        "domestic": merged_domestic,
        "overseas": merged_overseas,
        "total_value_krw": merged_domestic["total_value_krw"],
        "total_invested_krw": merged_domestic["invested_krw"],
        "unrealized_pnl_krw": merged_domestic["pnl_krw"],
        "stock_return_pct": stock_return_pct,
        "is_mock": is_mock,
        "accounts": account_details,
    }


def _empty_overview() -> dict:
    return {
        "total_assets_krw": 0,
        "total_stock_krw": 0,
        "total_non_stock_krw": 0,
        "total_invested_krw": 0,
        "unrealized_pnl_krw": 0,
        "stock_return_pct": 0,
        "asset_type_allocation": [],
        "stock_allocation": [],
        "all_positions": [],
        "accounts": [],
    }
