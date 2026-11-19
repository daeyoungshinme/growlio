"""포트폴리오 조회 쿼리 헬퍼."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.asset import RebalancingExecution
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


async def get_active_alerts_by_portfolio(db: AsyncSession, user_id: uuid.UUID) -> dict[str, list[RebalancingAlert]]:
    """활성 리밸런싱 알림을 portfolio_id(str)별로 묶어 반환한다.

    PER_ACCOUNT 스코프 포트폴리오는 계좌별 알림이 여럿일 수 있다 — 대표 기준은 `alert_drift_thresholds`로.
    """
    rows = (
        (
            await db.execute(
                select(RebalancingAlert).where(
                    RebalancingAlert.user_id == user_id,
                    RebalancingAlert.is_active == True,
                )
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[RebalancingAlert]] = {}
    for alert in rows:
        grouped.setdefault(str(alert.portfolio_id), []).append(alert)
    return grouped


DEFAULT_DRIFT_THRESHOLD_PCT = 5.0


def alert_drift_thresholds(alerts: list[RebalancingAlert]) -> tuple[float, float | None]:
    """포트폴리오 알림들의 대표 (절대 %p, 상대 %) 기준 — 둘 다 가장 먼저 트리거되는 최솟값.

    알림이 없으면 (5.0, None). 상대 기준은 켠 알림이 하나도 없으면 None(끔).
    """
    if not alerts:
        return DEFAULT_DRIFT_THRESHOLD_PCT, None
    threshold = min(float(a.threshold_pct) for a in alerts)
    relatives = [float(a.relative_threshold_pct) for a in alerts if a.relative_threshold_pct is not None]
    return threshold, (min(relatives) if relatives else None)


async def get_last_rebalanced_at(db: AsyncSession, user_id: uuid.UUID) -> dict[str, datetime]:
    """portfolio_id(str) → 주문이 한 건이라도 성공한 마지막 리밸런싱 실행 시각.

    전부 실패·건너뜀인 실행은 리밸런싱한 것이 아니므로 뺀다. 삭제된 포트폴리오(portfolio_id NULL)도 뺀다.
    """
    result = await db.execute(
        select(RebalancingExecution.portfolio_id, func.max(RebalancingExecution.executed_at))
        .where(
            RebalancingExecution.user_id == user_id,
            RebalancingExecution.portfolio_id.is_not(None),
            RebalancingExecution.total_success > 0,
        )
        .group_by(RebalancingExecution.portfolio_id)
    )
    return {str(portfolio_id): executed_at for portfolio_id, executed_at in result.all() if executed_at is not None}
