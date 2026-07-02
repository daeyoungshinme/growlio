"""포트폴리오 조회 쿼리 헬퍼."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio, PortfolioAccount


async def get_linked_portfolios(db: AsyncSession, user_id: uuid.UUID) -> list[Portfolio]:
    """계좌가 연결된 포트폴리오 목록을 items/linked_accounts와 함께 조회한다."""
    linked_ids_result = await db.execute(
        select(PortfolioAccount.portfolio_id)
        .join(Portfolio, Portfolio.id == PortfolioAccount.portfolio_id)
        .where(Portfolio.user_id == user_id)
        .distinct()
    )
    linked_portfolio_ids = linked_ids_result.scalars().all()
    if not linked_portfolio_ids:
        return []

    portfolios_result = await db.execute(
        select(Portfolio)
        .options(
            selectinload(Portfolio.items),
            selectinload(Portfolio.linked_accounts),
        )
        .where(Portfolio.id.in_(linked_portfolio_ids))
    )
    return list(portfolios_result.scalars().all())


async def get_active_alert_thresholds(db: AsyncSession, user_id: uuid.UUID) -> dict[str, float]:
    """활성 리밸런싱 알림의 portfolio_id → threshold_pct 매핑을 반환한다."""
    alerts_result = await db.execute(
        select(RebalancingAlert).where(
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.is_active == True,  # noqa: E712
        )
    )
    return {str(a.portfolio_id): float(a.threshold_pct) for a in alerts_result.scalars().all()}
