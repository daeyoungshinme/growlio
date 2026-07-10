"""포트폴리오 조회 쿼리 헬퍼."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
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
    """활성 리밸런싱 알림의 portfolio_id → threshold_pct(최솟값) 매핑을 반환한다.

    PER_ACCOUNT 스코프 포트폴리오는 계좌별로 서로 다른 threshold_pct를 가진 여러 행을
    가질 수 있으므로, 가장 보수적인(가장 먼저 트리거되는) 값을 대표값으로 사용한다.
    """
    result = await db.execute(
        select(RebalancingAlert.portfolio_id, func.min(RebalancingAlert.threshold_pct))
        .where(
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.is_active == True,  # noqa: E712
        )
        .group_by(RebalancingAlert.portfolio_id)
    )
    return {str(portfolio_id): float(min_threshold) for portfolio_id, min_threshold in result.all()}
