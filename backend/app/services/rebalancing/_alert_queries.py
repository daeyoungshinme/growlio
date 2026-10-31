"""리밸런싱 알림(RebalancingAlert) 조회 쿼리 헬퍼."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings


def alert_scope_filter(account_id: uuid.UUID | None) -> ColumnElement[bool]:
    """account_id가 있으면 그 계좌의 PER_ACCOUNT 행, 없으면 AGGREGATE 행.

    account_id 컬럼은 AGGREGATE에서도 AUTO면 채워지므로 스코프 판별엔 `alert_scope`를 함께 본다.
    """
    if account_id is not None:
        return (RebalancingAlert.alert_scope == "PER_ACCOUNT") & (RebalancingAlert.account_id == account_id)
    return RebalancingAlert.alert_scope == "AGGREGATE"


def alert_with_recipient_stmt(*extra_columns: Any) -> Select:
    """(알림, 포트폴리오(연결계좌·항목 로드), 가입 이메일, 알림 이메일, fcm_token, *extra_columns) 조회문.

    드리프트 알림 체크·AUTO 플랜 생성 job·테스트 발송이 같은 행 모양을 쓴다. 조건은 호출부가 `.where()`로 붙인다.
    """
    return (
        select(
            RebalancingAlert,
            Portfolio,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
            *extra_columns,
        )
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
    )


async def get_alert_by_portfolio(
    db: AsyncSession, portfolio_id: uuid.UUID, user_id: uuid.UUID
) -> RebalancingAlert | None:
    """AGGREGATE 스코프 알림 행(alert_scope == "AGGREGATE")을 조회한다.

    account_id는 AGGREGATE 스코프에서도 AUTO 모드면 NOT NULL이 되므로 스코프 판별에 쓸 수 없다
    — 반드시 alert_scope 컬럼으로 필터링해 PER_ACCOUNT 행이 섞여 들어오는 것을 막는다
    (db.scalar()은 다중 행에도 예외를 던지지 않고 첫 행만 반환).
    """
    return await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.alert_scope == "AGGREGATE",
        )
    )


async def get_alert_by_portfolio_and_account(
    db: AsyncSession, portfolio_id: uuid.UUID, account_id: uuid.UUID, user_id: uuid.UUID
) -> RebalancingAlert | None:
    """PER_ACCOUNT 스코프의 특정 계좌 전용 알림 행을 조회한다."""
    return await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.alert_scope == "PER_ACCOUNT",
            RebalancingAlert.account_id == account_id,
        )
    )


async def list_alerts_by_portfolio_accounts(
    db: AsyncSession, portfolio_id: uuid.UUID, user_id: uuid.UUID
) -> list[RebalancingAlert]:
    """PER_ACCOUNT 스코프 포트폴리오의 계좌별 알림 행 목록을 조회한다."""
    result = await db.execute(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.alert_scope == "PER_ACCOUNT",
        )
    )
    return list(result.scalars().all())
