"""리밸런싱 알림(RebalancingAlert) 조회 쿼리 헬퍼."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import RebalancingAlert


async def get_alert_by_portfolio(
    db: AsyncSession, portfolio_id: uuid.UUID, user_id: uuid.UUID
) -> RebalancingAlert | None:
    return await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
        )
    )
