"""포지션 집계 유틸리티 — 최신 스냅샷에서 ticker+market 기준 포지션 맵을 구성한다."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services._snapshot_queries import latest_snapshot_subquery


async def query_latest_position_map(
    user_id: uuid.UUID,
    db: AsyncSession,
    include_name: bool = False,
    account_ids: list[uuid.UUID] | None = None,
) -> dict[str, dict]:
    """사용자의 최신 스냅샷 포지션을 ticker-market 키로 집계한다.

    account_ids가 주어지면 해당 계좌만 집계한다.

    Returns:
        {"{ticker}-{market}": {"ticker": ..., "market": ..., "value_krw": ..., ["name": ...]}}
    """
    subq = latest_snapshot_subquery(user_id=user_id)
    q = (
        select(AssetSnapshot, AssetAccount)
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id) & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    if account_ids:
        q = q.where(AssetAccount.id.in_(account_ids))
    result = await db.execute(q)
    rows = result.all()

    snap_ids = [snap.id for snap, _ in rows]
    pos_map: dict[str, dict] = {}
    if snap_ids:
        all_pos_result = await db.execute(select(Position).where(Position.snapshot_id.in_(snap_ids)))
        for pos in all_pos_result.scalars().all():
            key = f"{pos.ticker}-{pos.market}"
            if key not in pos_map:
                entry: dict = {"ticker": pos.ticker, "market": pos.market, "value_krw": 0.0}
                if include_name:
                    entry["name"] = pos.name or pos.ticker
                pos_map[key] = entry
            pos_map[key]["value_krw"] += float(pos.value_krw or 0)

    return pos_map
