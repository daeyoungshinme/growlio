"""리밸런싱 알림 alert_scope(AGGREGATE ↔ PER_ACCOUNT) 전환."""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.services.rebalancing._alert_queries import get_alert_by_portfolio, list_alerts_by_portfolio_accounts

__all__ = ["resolve_effective_account_ids", "switch_alert_scope"]


def resolve_effective_account_ids(alert: RebalancingAlert, portfolio: Portfolio) -> list[uuid.UUID] | None:
    """알림이 분석 대상으로 삼을 계좌 범위를 결정한다.

    portfolio.alert_scope로만 분기한다 — alert.account_id의 NULL 여부로 분기하면 안 된다
    (AGGREGATE 스코프의 AUTO 알림도 이미 account_id가 NOT NULL이라 오판 위험).
    """
    if getattr(portfolio, "alert_scope", "AGGREGATE") == "PER_ACCOUNT" and alert.account_id is not None:
        return [alert.account_id]
    saved_ids = getattr(portfolio, "account_ids", None)
    return [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None


async def switch_alert_scope(db: AsyncSession, portfolio: Portfolio, target_scope: str) -> None:
    """포트폴리오의 alert_scope를 AGGREGATE ↔ PER_ACCOUNT로 전환한다.

    AGGREGATE→PER_ACCOUNT: 기존 AGGREGATE 행이 있고 그 account_id(AUTO 모드였던 경우의 실행계좌)가
    연결 계좌에 속하면 그대로 승계해 그 계좌 전용 PER_ACCOUNT 행이 되도록 alert_scope를 갱신한다.
    그 외(NOTIFY라 account_id가 없거나 연결 계좌 밖)면 행을 삭제한다 — 나머지 계좌는 사용자가
    화면에서 개별로 추가해야 한다.
    PER_ACCOUNT→AGGREGATE: 기존 PER_ACCOUNT 행을 전부 삭제한다(어느 계좌 설정을 aggregate로
    승격할지 모호하므로 승계하지 않음) — 새 AGGREGATE 설정은 사용자가 처음부터 구성한다.
    `portfolio.linked_accounts`가 selectinload되어 있어야 한다.
    """
    if target_scope not in ("AGGREGATE", "PER_ACCOUNT"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="알 수 없는 alert_scope입니다")

    current_scope = getattr(portfolio, "alert_scope", "AGGREGATE")
    if current_scope == target_scope:
        return

    linked_account_ids = {pa.account_id for pa in portfolio.linked_accounts}

    if target_scope == "PER_ACCOUNT":
        if len(linked_account_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="계좌별 독립 설정은 연결된 계좌가 2개 이상이어야 합니다",
            )
        aggregate_alert = await get_alert_by_portfolio(db, portfolio.id, portfolio.user_id)
        if aggregate_alert and aggregate_alert.account_id in linked_account_ids:
            aggregate_alert.alert_scope = "PER_ACCOUNT"  # 연결 계좌 소속 실행계좌 — 그 계좌 전용 행으로 승계
        elif aggregate_alert:
            await db.delete(aggregate_alert)
    else:
        per_account_alerts = await list_alerts_by_portfolio_accounts(db, portfolio.id, portfolio.user_id)
        for alert in per_account_alerts:
            await db.delete(alert)

    portfolio.alert_scope = target_scope
    await db.commit()
