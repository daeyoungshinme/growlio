from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetSnapshot, Position


async def _upsert_snapshot(
    db: AsyncSession,
    *,
    account_id,
    user_id,
    snapshot_date,
    amount_krw,
    source,
    **kwargs,
) -> AssetSnapshot:
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
    return result.scalar_one()


async def sync_snapshot_positions(
    db: AsyncSession,
    *,
    snapshot_id: uuid.UUID,
    account_id: uuid.UUID,
    positions: list[Any],
) -> None:
    """스냅샷 포지션을 초기화하고 positions를 복사한다.

    positions 원소는 .ticker/.name/.market/.qty/.avg_price/.avg_price_usd/
    .current_price/.value_krw/.currency/.usd_rate 속성을 가져야 한다.
    commit은 호출자가 처리한다.
    """
    # Row-level lock to prevent concurrent syncs for the same snapshot.
    await db.execute(select(AssetSnapshot).where(AssetSnapshot.id == snapshot_id).with_for_update())
    await db.execute(sql_delete(Position).where(Position.snapshot_id == snapshot_id))
    for p in positions:
        db.add(
            Position(
                account_id=account_id,
                snapshot_id=snapshot_id,
                ticker=p.ticker,
                name=p.name,
                market=p.market,
                qty=p.qty,
                avg_price=p.avg_price,
                avg_price_usd=p.avg_price_usd,
                current_price=p.current_price,
                value_krw=p.value_krw,
                currency=p.currency,
                usd_rate=p.usd_rate,
            )
        )
