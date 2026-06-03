"""포트폴리오 overview 집계 서비스 (portfolio.py 라우터에서 분리)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AssetType
from app.models.asset import AssetAccount, AssetSnapshot, Position

ASSET_TYPE_LABELS: dict[str, str] = {
    AssetType.BANK_ACCOUNT: "통장잔고",
    AssetType.DEPOSIT: "예금/적금",
    AssetType.STOCK_KIS: "주식(KIS)",
    AssetType.STOCK_OTHER: "주식(타증권)",
    AssetType.CASH_OTHER: "예수금(기타)",
    AssetType.OTHER: "기타자산",
    AssetType.REAL_ESTATE: "부동산",
}

STOCK_TYPES: frozenset[str] = frozenset({AssetType.STOCK_KIS, AssetType.STOCK_OTHER})


async def _fetch_latest_snapshots(
    acc_ids: list[uuid.UUID], db: AsyncSession
) -> dict[str, AssetSnapshot]:
    """계좌 ID 목록의 최신 스냅샷을 {account_id_str: snapshot} 딕셔너리로 반환한다."""
    subq = (
        select(AssetSnapshot.account_id, func.max(AssetSnapshot.snapshot_date).label("max_date"))
        .where(AssetSnapshot.account_id.in_(acc_ids))
        .group_by(AssetSnapshot.account_id)
        .subquery()
    )
    result = await db.execute(
        select(AssetSnapshot).join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id)
            & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
    )
    return {str(s.account_id): s for s in result.scalars().all()}


def _calc_account_amounts(
    acc: AssetAccount,
    snap: AssetSnapshot | None,
    positions: list[Position],
) -> tuple[float, float, float, list[Position]]:
    """(amount_krw, invested_krw, unrealized_pnl, positions) 계산."""
    if snap:
        amount_krw = float(snap.amount_krw)
        if snap.invested_amount is not None:
            return amount_krw, float(snap.invested_amount), float(snap.unrealized_pnl or 0), positions
        invested = sum(float(p.avg_price or 0) * float(p.qty or 0) for p in positions)
        value = sum((float(p.current_price) if p.current_price else float(p.avg_price or 0)) * float(p.qty or 0) for p in positions)
        return amount_krw, invested, (value - invested if positions else 0.0), positions

    if acc.manual_amount is not None:
        if acc.asset_type == "REAL_ESTATE":
            mortgage = float((acc.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
            amount_krw = float(acc.manual_amount) - mortgage
        else:
            amount_krw = float(acc.manual_amount)
        invested = sum(float(p.avg_price or 0) * float(p.qty or 0) for p in positions)
        value = sum((float(p.current_price) if p.current_price else float(p.avg_price or 0)) * float(p.qty or 0) for p in positions)
        return amount_krw, invested, (value - invested if positions else 0.0), positions

    return 0.0, 0.0, 0.0, []


def _build_position_details(
    acc: AssetAccount, raw_positions: list[Position], snap: AssetSnapshot | None
) -> list[dict]:
    """주식 계좌의 종목 상세 목록을 계산해 반환한다."""
    if acc.asset_type not in STOCK_TYPES or not raw_positions:
        return []
    result = []
    for p in raw_positions:
        qty = float(p.qty or 0)
        avg_out = float(p.avg_price or 0)
        cur_out = float(p.current_price or p.avg_price or 0)
        val_amt = float(p.value_krw or cur_out * qty)
        inv_amt = avg_out * qty
        pnl_p = val_amt - inv_amt
        result.append({
            "ticker": p.ticker,
            "name": p.name or "",
            "market": p.market,
            "qty": qty,
            "avg_price": avg_out,
            "current_price": cur_out,
            "value_krw": val_amt,
            "invested_krw": inv_amt,
            "pnl": pnl_p,
            "pnl_pct": round((pnl_p / inv_amt * 100) if inv_amt else 0.0, 2),
            "currency": p.currency or "KRW",
            "account_id": str(acc.id),
            "account_name": acc.name,
        })
    return result


def _build_stock_allocation(all_positions: list[dict], stock_total_krw: float) -> list[dict]:
    """동일 ticker+market 합산 후 상위 10종목 + 기타를 반환한다 (차트용)."""
    ticker_merged: dict[str, dict] = {}
    for p in all_positions:
        key = f"{p['ticker']}-{p['market']}"
        if key not in ticker_merged:
            ticker_merged[key] = {"ticker": p["ticker"], "name": p["name"], "value_krw": 0.0}
        ticker_merged[key]["value_krw"] += p["value_krw"]

    sorted_merged = sorted(ticker_merged.values(), key=lambda x: -x["value_krw"])
    top, rest = sorted_merged[:10], sorted_merged[10:]
    allocation = [
        {
            "ticker": p["ticker"],
            "name": p["name"],
            "value_krw": p["value_krw"],
            "pct": round(p["value_krw"] / stock_total_krw * 100, 2) if stock_total_krw else 0,
        }
        for p in top
    ]
    if rest:
        rest_value = sum(p["value_krw"] for p in rest)
        allocation.append({
            "ticker": "ETC",
            "name": f"기타 {len(rest)}종목",
            "value_krw": rest_value,
            "pct": round(rest_value / stock_total_krw * 100, 2) if stock_total_krw else 0,
        })
    return allocation


async def build_portfolio_overview(
    user_id: uuid.UUID,
    db: AsyncSession,
    account_ids: list[uuid.UUID] | None = None,
) -> dict:
    """포트폴리오 전체 현황 집계 (라우터 및 분석 엔드포인트에서 공용)."""
    query = (
        select(AssetAccount)
        .where(AssetAccount.user_id == user_id, AssetAccount.is_active == True)  # noqa: E712
        .order_by(AssetAccount.sort_order, AssetAccount.created_at)
    )
    if account_ids:
        query = query.where(AssetAccount.id.in_(account_ids))
    acc_result = await db.execute(query)
    accounts: list[AssetAccount] = list(acc_result.scalars().all())
    if not accounts:
        return _empty_overview()

    snap_by_acc = await _fetch_latest_snapshots([a.id for a in accounts], db)

    # 스냅샷 포지션 미리 로드 (snapshot_id → [Position])
    snap_ids = [s.id for s in snap_by_acc.values()]
    acc_ids = [a.id for a in accounts if a.asset_type in STOCK_TYPES]
    snap_pos_map: dict[Any, list[Position]] = {}
    cur_pos_map: dict[Any, list[Position]] = {}

    if snap_ids:
        sp_result = await db.execute(
            select(Position).where(Position.snapshot_id.in_(snap_ids))
        )
        for pos in sp_result.scalars().all():
            snap_pos_map.setdefault(pos.snapshot_id, []).append(pos)

    if acc_ids:
        cp_result = await db.execute(
            select(Position).where(
                Position.account_id.in_(acc_ids),
                Position.snapshot_id == None,  # noqa: E711
            )
        )
        for pos in cp_result.scalars().all():
            cur_pos_map.setdefault(pos.account_id, []).append(pos)

    total_assets_krw = 0.0
    total_invested_krw = 0.0
    unrealized_pnl_krw = 0.0
    asset_type_totals: dict[str, float] = {}
    all_positions: list[dict] = []
    account_rows: list[dict] = []

    for acc in accounts:
        snap = snap_by_acc.get(str(acc.id))
        pos_list_db: list[Position] = (
            snap_pos_map.get(snap.id, []) if snap else []
        ) or cur_pos_map.get(acc.id, [])
        amount_krw, invested, pnl, raw_positions = _calc_account_amounts(acc, snap, pos_list_db)

        if acc.include_in_total:
            total_assets_krw += amount_krw
            asset_type_totals[acc.asset_type] = asset_type_totals.get(acc.asset_type, 0) + amount_krw
        if acc.asset_type in STOCK_TYPES:
            total_invested_krw += invested
            unrealized_pnl_krw += pnl

        pos_list = _build_position_details(acc, raw_positions, snap)
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

    stock_total_krw = total_invested_krw + unrealized_pnl_krw
    stock_return_pct = (unrealized_pnl_krw / total_invested_krw * 100) if total_invested_krw else 0.0

    for p in all_positions:
        p["weight_in_stock"] = round(p["value_krw"] / stock_total_krw * 100, 2) if stock_total_krw else 0

    asset_type_allocation = [
        {
            "type": t,
            "label": ASSET_TYPE_LABELS.get(t, t),
            "amount_krw": v,
            "pct": round(v / total_assets_krw * 100, 2) if total_assets_krw else 0,
        }
        for t, v in sorted(asset_type_totals.items(), key=lambda x: -x[1])
    ]

    return {
        "total_assets_krw": total_assets_krw,
        "total_stock_krw": stock_total_krw,
        "total_non_stock_krw": total_assets_krw - stock_total_krw,
        "total_invested_krw": total_invested_krw,
        "unrealized_pnl_krw": unrealized_pnl_krw,
        "stock_return_pct": round(stock_return_pct, 2),
        "asset_type_allocation": asset_type_allocation,
        "stock_allocation": _build_stock_allocation(all_positions, stock_total_krw),
        "all_positions": all_positions,
        "accounts": account_rows,
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


_EXTENDED_ASSET_TYPE_LABELS: dict[str, str] = {
    AssetType.BANK_ACCOUNT: "통장잔고",
    AssetType.DEPOSIT: "예금/적금",
    AssetType.STOCK_KIS: "주식",
    AssetType.STOCK_KIWOOM: "주식",
    AssetType.STOCK_OTHER: "주식",
    AssetType.CASH_OTHER: "예수금",
    AssetType.CASH_STOCK: "예수금",
    AssetType.OTHER: "기타자산",
    AssetType.REAL_ESTATE: "부동산",
}


async def get_allocation_history(
    user_id: uuid.UUID, db: AsyncSession, months: int = 12
) -> list[dict]:
    """월별 자산 유형별 배분 이력 조회.

    각 월의 마지막 스냅샷 기준으로 asset_type별 금액/비중을 반환한다.
    is_active = TRUE 필터 필수 — 비활성 계좌 스냅샷 합산 방지.
    """
    today = date.today()
    # months=12이면 현재 월 포함 12개월 (오늘 기준 11개월 전 1일)
    start_month = today.month - (months - 1)
    start_year = today.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start_date = date(start_year, start_month, 1)

    result = await db.execute(
        text("""
            WITH ranked AS (
                SELECT
                    date_trunc('month', s.snapshot_date)::date AS month,
                    a.asset_type,
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
                    AND s.snapshot_date >= :start_date
            )
            SELECT month, asset_type, SUM(amount_krw) AS amount_krw
            FROM ranked
            WHERE rn = 1
            GROUP BY month, asset_type
            ORDER BY month, asset_type
        """),
        {"uid": str(user_id), "start_date": start_date},
    )
    rows = result.all()

    # 월별로 그룹화
    monthly: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        month_str = str(row.month)
        monthly[month_str][row.asset_type] += float(row.amount_krw)

    output = []
    for month_str in sorted(monthly.keys()):
        type_amounts = monthly[month_str]
        total_krw = sum(type_amounts.values())
        if total_krw <= 0:
            continue

        allocations = []
        for asset_type, amount_krw in sorted(type_amounts.items()):
            allocations.append({
                "asset_type": asset_type,
                "label": _EXTENDED_ASSET_TYPE_LABELS.get(asset_type, asset_type),
                "amount_krw": round(amount_krw, 2),
                "weight_pct": round(amount_krw / total_krw * 100, 2),
            })

        output.append({
            "month": month_str,
            "total_krw": round(total_krw, 2),
            "allocations": allocations,
        })

    return output
