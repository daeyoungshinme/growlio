"""포트폴리오 overview 집계 서비스 (portfolio.py 라우터에서 분리)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOMESTIC_MARKETS
from app.enums import AssetType
from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services._account_queries import active_accounts_stmt
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.composition_calculator import fetch_position_maps
from app.utils.cache_keys import (
    TTL_PORTFOLIO_OVERVIEW,
    RedisType,
    get_cached_json,
    portfolio_overview_acct_suffix,
    portfolio_overview_key,
    portfolio_overview_lite_key,
    set_cached_json,
)
from app.utils.pnl import calc_net_asset_amount, calc_position_pnl

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

# 브로커 계좌: deposit_krw를 보유하는 유형 (예수금 합산 대상)
_BROKER_TYPES: frozenset[str] = frozenset({AssetType.STOCK_KIS, AssetType.STOCK_KIWOOM, AssetType.STOCK_OTHER})


async def _fetch_latest_snapshots(acc_ids: list[uuid.UUID], db: AsyncSession) -> dict[str, AssetSnapshot]:
    """계좌 ID 목록의 최신 스냅샷을 {account_id_str: snapshot} 딕셔너리로 반환한다."""
    subq = latest_snapshot_subquery(account_ids=acc_ids)
    result = await db.execute(
        select(AssetSnapshot).join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date),
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
        value = sum(
            (float(p.current_price) if p.current_price else float(p.avg_price or 0)) * float(p.qty or 0)
            for p in positions
        )
        return amount_krw, invested, (value - invested if positions else 0.0), positions

    if acc.manual_amount is not None:
        amount_krw = calc_net_asset_amount(acc.manual_amount, acc.asset_type, acc.real_estate_details)
        invested = sum(float(p.avg_price or 0) * float(p.qty or 0) for p in positions)
        value = sum(
            (float(p.current_price) if p.current_price else float(p.avg_price or 0)) * float(p.qty or 0)
            for p in positions
        )
        return amount_krw, invested, (value - invested if positions else 0.0), positions

    return 0.0, 0.0, 0.0, []


def _build_position_details(acc: AssetAccount, raw_positions: list[Position], snap: AssetSnapshot | None) -> list[dict]:
    """주식 계좌의 종목 상세 목록을 계산해 반환한다."""
    if acc.asset_type not in STOCK_TYPES or not raw_positions:
        return []
    result = []
    for p in raw_positions:
        qty = float(p.qty or 0)
        avg_out = float(p.avg_price or 0)
        cur_out = float(p.current_price or p.avg_price or 0)
        val_amt = float(p.value_krw or cur_out * qty)
        inv_amt, _, pnl_p, rate = calc_position_pnl(qty, avg_out, cur_out)
        result.append(
            {
                "ticker": p.ticker,
                "name": p.name or "",
                "market": p.market,
                "qty": qty,
                "avg_price": avg_out,
                "current_price": cur_out,
                "value_krw": val_amt,
                "invested_krw": inv_amt,
                "pnl": pnl_p,
                "pnl_pct": round(rate, 2),
                "currency": p.currency or "KRW",
                "account_id": str(acc.id),
                "account_name": acc.name,
            }
        )
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
        allocation.append(
            {
                "ticker": "ETC",
                "name": f"기타 {len(rest)}종목",
                "value_krw": rest_value,
                "pct": round(rest_value / stock_total_krw * 100, 2) if stock_total_krw else 0,
            }
        )
    return allocation


def _accumulate_account_totals(
    acc: AssetAccount,
    amount_krw: float,
    invested: float,
    pnl: float,
    total_assets_krw: float,
    total_invested_krw: float,
    unrealized_pnl_krw: float,
    asset_type_totals: dict[str, float],
) -> tuple[float, float, float]:
    """계좌 금액을 전체 합계에 누적하고 갱신된 (total_assets, total_invested, unrealized_pnl)을 반환한다."""
    if acc.include_in_total:
        total_assets_krw += amount_krw
        asset_type_totals[acc.asset_type] = asset_type_totals.get(acc.asset_type, 0) + amount_krw
    if acc.asset_type in STOCK_TYPES:
        total_invested_krw += invested
        unrealized_pnl_krw += pnl
    return total_assets_krw, total_invested_krw, unrealized_pnl_krw


def _build_account_row(
    acc: AssetAccount,
    snap: AssetSnapshot | None,
    raw_positions: list[Position],
    amount_krw: float,
    invested: float,
    pnl: float,
    lite: bool,
    all_positions: list[dict],
    lite_stock_items: list[dict],
) -> dict:
    """계좌 row 딕셔너리를 구성하고 all_positions / lite_stock_items 를 갱신한다."""
    if lite:
        pos_list: list[dict] = []
        if acc.asset_type in STOCK_TYPES:
            for p in raw_positions:
                cur_p = float(p.current_price or p.avg_price or 0)
                val = float(p.value_krw or cur_p * float(p.qty or 0))
                lite_stock_items.append(
                    {"ticker": p.ticker, "name": p.name or "", "market": p.market, "value_krw": val}
                )
    else:
        pos_list = _build_position_details(acc, raw_positions, snap)
        all_positions.extend(pos_list)

    account_row: dict = {
        "id": str(acc.id),
        "name": acc.name,
        "asset_type": acc.asset_type,
        "asset_type_label": ASSET_TYPE_LABELS.get(acc.asset_type, acc.asset_type),
        "data_source": acc.data_source,
        "institution": acc.institution,
        "tax_type": acc.tax_type,
        "investment_horizon": acc.investment_horizon,
        "amount_krw": amount_krw,
        "invested_krw": invested,
        "unrealized_pnl": pnl,
        "position_count": len(raw_positions),
        "positions": pos_list,
        "include_in_total": acc.include_in_total,
    }
    if acc.asset_type == "REAL_ESTATE":
        account_row["real_estate_details"] = acc.real_estate_details
        account_row["market_value_krw"] = float(acc.manual_amount or 0)
    return account_row


async def build_portfolio_overview(
    user_id: uuid.UUID,
    db: AsyncSession,
    account_ids: list[uuid.UUID] | None = None,
    redis: RedisType = None,
    lite: bool = False,
) -> dict[str, Any]:
    """포트폴리오 전체 현황 집계 (라우터 및 분석 엔드포인트에서 공용).

    lite=True 시 all_positions / accounts[].positions 를 생략해 응답 크기를 대폭 줄인다.
    대시보드에서 사용하며, 전체 종목 목록이 필요한 포트폴리오 페이지는 lite=False(기본값) 사용.
    """
    cache_key_fn = portfolio_overview_lite_key if lite else portfolio_overview_key
    acct_suffix = portfolio_overview_acct_suffix(account_ids)
    cached = await get_cached_json(redis, cache_key_fn(user_id, acct_suffix))
    if cached is not None:
        return cached

    query = active_accounts_stmt(user_id).order_by(AssetAccount.sort_order, AssetAccount.created_at)
    if account_ids:
        query = query.where(AssetAccount.id.in_(account_ids))
    acc_result = await db.execute(query)
    accounts: list[AssetAccount] = list(acc_result.scalars().all())
    if not accounts:
        return _empty_overview()

    snap_by_acc = await _fetch_latest_snapshots([a.id for a in accounts], db)

    snap_ids = [s.id for s in snap_by_acc.values()]
    acc_ids = [a.id for a in accounts if a.asset_type in STOCK_TYPES]
    snap_pos_map, cur_pos_map = await fetch_position_maps(snap_ids, acc_ids, db)

    total_assets_krw = 0.0
    total_invested_krw = 0.0
    unrealized_pnl_krw = 0.0
    total_deposit_krw = 0.0
    asset_type_totals: dict[str, float] = {}
    all_positions: list[dict] = []
    # lite 모드에서 stock_allocation 계산용 최소 필드만 수집
    lite_stock_items: list[dict] = []
    account_rows: list[dict] = []

    for acc in accounts:
        snap = snap_by_acc.get(str(acc.id))
        pos_list_db: list[Position] = (snap_pos_map.get(snap.id, []) if snap else []) or cur_pos_map.get(acc.id, [])
        amount_krw, invested, pnl, raw_positions = _calc_account_amounts(acc, snap, pos_list_db)

        total_assets_krw, total_invested_krw, unrealized_pnl_krw = _accumulate_account_totals(
            acc,
            amount_krw,
            invested,
            pnl,
            total_assets_krw,
            total_invested_krw,
            unrealized_pnl_krw,
            asset_type_totals,
        )

        account_row = _build_account_row(
            acc,
            snap,
            raw_positions,
            amount_krw,
            invested,
            pnl,
            lite,
            all_positions,
            lite_stock_items,
        )
        account_rows.append(account_row)

        if acc.asset_type in _BROKER_TYPES and acc.include_in_total:
            total_deposit_krw += float(acc.deposit_krw or 0)

    stock_total_krw = total_invested_krw + unrealized_pnl_krw
    stock_return_pct = (unrealized_pnl_krw / total_invested_krw * 100) if total_invested_krw else 0.0

    for alloc in all_positions:
        alloc["weight_in_stock"] = round(alloc["value_krw"] / stock_total_krw * 100, 2) if stock_total_krw else 0

    asset_type_allocation = [
        {
            "type": t,
            "label": ASSET_TYPE_LABELS.get(t, t),
            "amount_krw": v,
            "pct": round(v / total_assets_krw * 100, 2) if total_assets_krw else 0,
        }
        for t, v in sorted(asset_type_totals.items(), key=lambda x: -x[1])
    ]

    stock_alloc_source = lite_stock_items if lite else all_positions
    domestic_stock_krw = sum(p["value_krw"] for p in stock_alloc_source if p.get("market") in DOMESTIC_MARKETS)
    foreign_stock_krw = sum(p["value_krw"] for p in stock_alloc_source if p.get("market") not in DOMESTIC_MARKETS)
    overview = {
        "total_assets_krw": total_assets_krw,
        "total_stock_krw": stock_total_krw,
        "total_non_stock_krw": total_assets_krw - stock_total_krw,
        "total_invested_krw": total_invested_krw,
        "unrealized_pnl_krw": unrealized_pnl_krw,
        "stock_return_pct": round(stock_return_pct, 2),
        "domestic_stock_krw": domestic_stock_krw,
        "foreign_stock_krw": foreign_stock_krw,
        "total_deposit_krw": total_deposit_krw,
        "asset_type_allocation": asset_type_allocation,
        "stock_allocation": _build_stock_allocation(stock_alloc_source, stock_total_krw),
        "all_positions": all_positions,
        "accounts": account_rows,
    }

    await set_cached_json(redis, cache_key_fn(user_id, acct_suffix), overview, TTL_PORTFOLIO_OVERVIEW)
    return overview


def _empty_overview() -> dict[str, Any]:
    return {
        "total_assets_krw": 0,
        "total_stock_krw": 0,
        "total_non_stock_krw": 0,
        "total_invested_krw": 0,
        "unrealized_pnl_krw": 0,
        "stock_return_pct": 0,
        "domestic_stock_krw": 0,
        "foreign_stock_krw": 0,
        "total_deposit_krw": 0.0,
        "asset_type_allocation": [],
        "stock_allocation": [],
        "all_positions": [],
        "accounts": [],
    }
