"""원클릭 "지금 테스트 실행" — 저장된(또는 화면 미저장) 자동화 알림 설정으로 대기 플랜을 즉시 생성.

실제 스케줄 AUTO 실행과 동일한 파이프라인(드리프트 분석 → 대기 플랜 생성 → 계획 안내 이메일 발송)을
태운다. 결과는 `QuickExecuteOutcome`(상태 enum + 메시지 조립용 원자료)으로 돌려주고, 사용자 노출
문구는 라우터(`api/v1/rebalancing_execution.py`)가 상태별로 조립한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.schemas.rebalancing import ExecutionPlanOverride
from app.services.rebalancing.order_builder import is_market_signal_blocking_auto_mode
from app.services.rebalancing.plan_service import (
    DailyValueCapBlocked,
    PlanGenerationInProgress,
    TaxGateBlocked,
    build_pending_plan_for_alert,
    has_pending_plan_for_alert,
    notify_plan_generated,
)

logger = structlog.get_logger()


class QuickExecuteStatus(StrEnum):
    ALREADY_PENDING = "ALREADY_PENDING"
    MARKET_BLOCKED = "MARKET_BLOCKED"
    TAX_BLOCKED = "TAX_BLOCKED"
    DAILY_CAP_BLOCKED = "DAILY_CAP_BLOCKED"
    GENERATION_IN_PROGRESS = "GENERATION_IN_PROGRESS"
    NO_DRIFT = "NO_DRIFT"
    PLAN_GENERATED = "PLAN_GENERATED"


@dataclass
class QuickExecuteOutcome:
    status: QuickExecuteStatus
    composite_level: str | None = None
    tax_gate: TaxGateBlocked | None = None
    daily_cap: DailyValueCapBlocked | None = None
    email_sent: bool = False
    has_email: bool = False
    plan_id: uuid.UUID | None = None
    buy_count: int = 0
    sell_count: int = 0


async def _load_portfolio(portfolio_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Portfolio:
    portfolio = await db.scalar(
        select(Portfolio)
        .options(
            selectinload(Portfolio.linked_accounts),
            selectinload(Portfolio.items),
        )
        .where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == user_id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")
    return portfolio


async def _load_alert_row(
    portfolio: Portfolio,
    portfolio_id: uuid.UUID,
    account_id: uuid.UUID | None,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> RebalancingAlert:
    is_per_account = getattr(portfolio, "alert_scope", "AGGREGATE") == "PER_ACCOUNT"
    if is_per_account and account_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="계좌별 독립 설정 포트폴리오는 account_id를 지정해야 합니다",
        )

    account_filter = (
        (RebalancingAlert.alert_scope == "PER_ACCOUNT") & (RebalancingAlert.account_id == account_id)
        if is_per_account
        else RebalancingAlert.alert_scope == "AGGREGATE"
    )
    alert_row = await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == user_id,
            RebalancingAlert.is_active == True,
            account_filter,
        )
    )
    if not alert_row or not alert_row.account_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="이 포트폴리오에 자동 실행 계좌가 설정되지 않았습니다. 자동화 설정에서 계좌를 선택해주세요.",
        )
    return alert_row


async def _notification_targets(user_id: uuid.UUID, db: AsyncSession) -> tuple[str | None, str | None]:
    """(수신 이메일, fcm_token) — 알림 전용 이메일이 있으면 그것을, 없으면 가입 이메일."""
    settings_row = await db.execute(
        select(User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == user_id)
    )
    user_email, notification_email, fcm_token = settings_row.first() or (None, None, None)
    return notification_email or user_email, fcm_token


async def quick_execute_plan(
    portfolio_id: uuid.UUID,
    account_id: uuid.UUID | None,
    body: ExecutionPlanOverride | None,
    user_id: uuid.UUID,
    db: AsyncSession,
    cache,
    verify_account_owned: Callable[[uuid.UUID], Awaitable[object]],
) -> QuickExecuteOutcome:
    """자동화 알림 설정 기준으로 대기 플랜을 생성한다 — 입력 오류는 HTTPException, 게이트 차단은 상태로 반환.

    `verify_account_owned`는 화면에서 고른 override 계좌의 소유권 검증(라우터의 `get_owned_account`) —
    서비스가 API 계층을 import하지 않도록 주입받는다.
    """
    from app.services.market_signal_service import get_confirmed_composite_level

    portfolio = await _load_portfolio(portfolio_id, user_id, db)
    alert_row = await _load_alert_row(portfolio, portfolio_id, account_id, user_id, db)

    if body and body.account_id and body.account_id != alert_row.account_id:
        await verify_account_owned(body.account_id)

    if await has_pending_plan_for_alert(alert_row.id, db):
        return QuickExecuteOutcome(QuickExecuteStatus.ALREADY_PENDING)

    try:
        composite_level, data_freshness = await get_confirmed_composite_level(cache, db)
    except Exception as exc:
        logger.warning("market_signal_fetch_failed_in_quick_execute", error=str(exc))
        composite_level = "GREEN"
        data_freshness = "STALE"

    market_mode = getattr(alert_row, "market_condition_mode", "DISABLED")
    if is_market_signal_blocking_auto_mode(market_mode, composite_level, data_freshness):
        return QuickExecuteOutcome(QuickExecuteStatus.MARKET_BLOCKED, composite_level=composite_level)

    generated = await build_pending_plan_for_alert(
        alert_row,
        portfolio,
        db,
        composite_level,
        strategy_override=body.strategy if body else None,
        order_type_override=body.order_type if body else None,
        account_id_override=body.account_id if body else None,
        cache=cache,
    )
    if isinstance(generated, TaxGateBlocked):
        return QuickExecuteOutcome(QuickExecuteStatus.TAX_BLOCKED, tax_gate=generated)
    if isinstance(generated, DailyValueCapBlocked):
        return QuickExecuteOutcome(QuickExecuteStatus.DAILY_CAP_BLOCKED, daily_cap=generated)
    if isinstance(generated, PlanGenerationInProgress):
        return QuickExecuteOutcome(QuickExecuteStatus.GENERATION_IN_PROGRESS)
    if generated is None:
        return QuickExecuteOutcome(QuickExecuteStatus.NO_DRIFT)
    plan, buy_tokens, sell_tokens = generated

    email, fcm_token = await _notification_targets(user_id, db)
    email_sent = await notify_plan_generated(
        plan,
        alert_row,
        portfolio,
        buy_tokens,
        sell_tokens,
        email,
        fcm_token,
        composite_level,
        db,
        note="수동 테스트",
    )
    await db.commit()

    return QuickExecuteOutcome(
        QuickExecuteStatus.PLAN_GENERATED,
        email_sent=email_sent,
        has_email=bool(email),
        plan_id=plan.id,
        buy_count=sum(len(leg.items) for leg in plan.legs if leg.side == "BUY"),
        sell_count=sum(len(leg.items) for leg in plan.legs if leg.side == "SELL"),
    )
