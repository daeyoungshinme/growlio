"""포지션 DB 쿼리 헬퍼 — 공통 쿼리를 한 곳에서 관리한다."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Position


async def fetch_manual_positions(account_id: UUID, db: AsyncSession) -> list[Position]:
    """스냅샷에 속하지 않는 수동 포지션(snapshot_id IS NULL)을 반환한다."""
    result = await db.execute(
        select(Position).where(
            Position.account_id == account_id,
            Position.snapshot_id == None,  # noqa: E711
        )
    )
    return list(result.scalars().all())
