"""자산 구성 계산 — 최신 스냅샷 기반 총자산·유형별 금액 집계."""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import AssetType
from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services._snapshot_queries import latest_snapshot_subquery
from app.utils.cache_keys import CacheStoreType
from app.utils.currency import fetch_usd_krw
from app.utils.pnl import calc_net_asset_amount as _calc_net_asset_amount
from app.utils.pnl import eval_value as _eval_value
from app.utils.pnl import invested_value as _invested_value

_STOCK_TYPES = {AssetType.STOCK_KIS, AssetType.STOCK_KIWOOM, AssetType.STOCK_OTHER}


async def get_latest_snapshot_rows(user_id: uuid.UUID, db: AsyncSession) -> tuple[list, set]:
    """활성 계좌의 최신 스냅샷 행과 스냅샷이 있는 계좌 ID 집합을 반환한다."""
    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(subq, (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date))
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    rows = result.all()
    snapped_ids = {acc.id for _, acc in rows}
    return list(rows), snapped_ids


async def get_no_snap_accounts(user_id: uuid.UUID, db: AsyncSession, snapped_ids: set) -> list:
    """스냅샷 없이 manual_amount/deposit만 있는 활성 계좌를 반환한다."""
    conditions = [
        AssetAccount.user_id == user_id,
        AssetAccount.is_active == True,  # noqa: E712
        or_(
            and_(AssetAccount.manual_amount.isnot(None), AssetAccount.manual_amount > 0),
            AssetAccount.deposit_krw > 0,
            AssetAccount.deposit_usd > 0,
        ),
    ]
    if snapped_ids:
        conditions.append(AssetAccount.id.not_in(snapped_ids))
    result = await db.execute(select(AssetAccount).where(*conditions))
    return list(result.scalars().all())


async def _fetch_snapshot_positions(snap_ids: list, db: AsyncSession) -> dict[uuid.UUID, list[Position]]:
    """스냅샷 포지션만 조회 (snapshot_id IN snap_ids)."""
    snap_positions: dict[uuid.UUID, list[Position]] = {}
    if snap_ids:
        pos_result = await db.execute(select(Position).where(Position.snapshot_id.in_(snap_ids)))
        for pos in pos_result.scalars().all():
            if pos.snapshot_id is not None:
                snap_positions.setdefault(pos.snapshot_id, []).append(pos)
    return snap_positions


async def _fetch_current_positions(stock_acc_ids: list, db: AsyncSession) -> dict[uuid.UUID, list[Position]]:
    """현재 포지션만 조회 (snapshot_id IS NULL, account_id IN stock_acc_ids)."""
    current_positions: dict[uuid.UUID, list[Position]] = {}
    if stock_acc_ids:
        cur_result = await db.execute(
            select(Position).where(
                Position.account_id.in_(stock_acc_ids),
                Position.snapshot_id == None,  # noqa: E711
            )
        )
        for pos in cur_result.scalars().all():
            current_positions.setdefault(pos.account_id, []).append(pos)
    return current_positions


async def fetch_position_maps(snap_ids: list, stock_acc_ids: list, db: AsyncSession) -> tuple[dict, dict]:
    """스냅샷별·계좌별 포지션을 각각 dict로 batch 조회한다."""
    snap_positions, current_positions = await asyncio.gather(
        _fetch_snapshot_positions(snap_ids, db),
        _fetch_current_positions(stock_acc_ids, db),
    )
    return snap_positions, current_positions


async def build_asset_totals(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType = None,
) -> tuple[float, float, float, dict[str, float]]:
    """최신 스냅샷 기준 총자산·투자금·주식평가액·유형별 금액을 집계한다.
    Returns: (total_assets_krw, total_invested, stock_value, by_type)
    """
    usd_rate = await fetch_usd_krw(cache)
    rows, snapped_ids = await get_latest_snapshot_rows(user_id, db)  # Q1

    snap_ids = [snap.id for snap, acc in rows if acc.asset_type in _STOCK_TYPES]
    stock_acc_ids_from_rows = [acc.id for _, acc in rows if acc.asset_type in _STOCK_TYPES]

    # Q2(no_snap 계좌 조회)와 Q3(스냅샷 포지션 조회)를 병렬 실행 — 두 쿼리는 서로 독립적
    no_snap_accounts, snap_positions = await asyncio.gather(
        get_no_snap_accounts(user_id, db, snapped_ids),
        _fetch_snapshot_positions(snap_ids, db),
    )

    # Q4: 현재 포지션 (no_snap 계좌 포함 전체 stock 계좌 대상)
    all_stock_acc_ids = stock_acc_ids_from_rows + [acc.id for acc in no_snap_accounts if acc.asset_type in _STOCK_TYPES]
    current_positions = await _fetch_current_positions(all_stock_acc_ids, db)

    total_assets_krw = 0.0
    total_invested = 0.0
    stock_value = 0.0
    by_type: dict[str, float] = {}

    for snap, acc in rows:
        if not acc.include_in_total:
            continue
        amount = float(snap.amount_krw)
        if acc.asset_type in _STOCK_TYPES:
            pos_list = snap_positions.get(snap.id) or current_positions.get(acc.id) or []
            if pos_list:
                stock_equity = _eval_value(pos_list)
                inv = float(snap.invested_amount or 0) or _invested_value(pos_list)
            else:
                # 종목 미보유 계좌: 잔액 전체가 예수금 — stock_equity를 0으로 처리해야
                # bank_total + total_invested 로 구성되는 base에서 금액 누락 방지
                stock_equity = 0.0
                inv = 0.0
            cash = amount - stock_equity
            stock_value += stock_equity
            total_invested += inv
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + stock_equity
            by_type["CASH_STOCK"] = by_type.get("CASH_STOCK", 0) + cash
        else:
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
            inv = _invested_value(pos_list) if pos_list else (0.0 if computed > 0 else float(acc.manual_amount or 0))
            # 예수금만 있는 경우(computed>0이지만 pos_equity=0)에는 stock_value에 추가하지 않음
            stock_value += pos_equity if (pos_list or computed > 0) else amount
            total_invested += inv
            if computed > 0:
                by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + pos_equity
                by_type["CASH_STOCK"] = by_type.get("CASH_STOCK", 0) + deposit
            else:
                by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        elif acc.asset_type == "REAL_ESTATE":
            amount = _calc_net_asset_amount(acc.manual_amount, acc.asset_type, acc.real_estate_details)
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        else:
            amount = float(acc.manual_amount or 0)
            by_type[acc.asset_type] = by_type.get(acc.asset_type, 0) + amount
        total_assets_krw += amount

    return total_assets_krw, total_invested, stock_value, by_type


def exclude_real_estate(total_assets_krw: float, by_type: dict[str, float]) -> float:
    """목표 진행율·필요수익률 등 '투자자산' 기준 계산에서 부동산 순자산을 제외한다.

    부동산은 목표 역산 추천(MVO)의 후보에 포함되지 않고 DCA 복리 곡선도 부동산 가치
    상승을 모델링하지 않으므로, 부동산을 포함한 총자산을 그대로 쓰면 부동산 추가만으로
    진행율이 왜곡된다. 대시보드 총자산/자산배분 등 순자산 표시에는 영향 없음(호출부 한정).
    """
    return total_assets_krw - by_type.get(AssetType.REAL_ESTATE, 0.0)
