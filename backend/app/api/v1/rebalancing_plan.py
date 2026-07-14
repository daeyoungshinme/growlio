"""리밸런싱 대기 플랜 조회/취소/승인 — 인증 필요 (앱 내 사용)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.limiter import limiter
from app.models.rebalancing_plan import RebalancingPlan, RebalancingPlanLeg
from app.models.user import User
from app.schemas.rebalancing import PlanActionResponse, RebalancingPlanItemOut, RebalancingPlanLegSummary
from app.services.rebalancing.plan_service import (
    approve_buy_leg,
    approve_sell_leg,
    cancel_buy_leg,
    list_recent_plan_legs,
    reject_sell_leg,
)

router = APIRouter(prefix="/rebalancing/plans", tags=["rebalancing-plans"])


def _build_summary(leg: RebalancingPlanLeg, plan: RebalancingPlan, portfolio_name, account_name):
    now = datetime.now(tz=UTC)
    deadline = leg.deadline_at if leg.deadline_at.tzinfo else leg.deadline_at.replace(tzinfo=UTC)
    return RebalancingPlanLegSummary(
        plan_id=plan.id,
        leg_id=leg.id,
        portfolio_id=plan.portfolio_id,
        portfolio_name=portfolio_name,
        account_id=plan.account_id,
        account_name=account_name,
        side=leg.side,
        status=leg.status,
        deadline_at=leg.deadline_at,
        decided_at=leg.decided_at,
        execution_id=leg.execution_id,
        error_message=leg.error_message,
        actionable=(leg.status == "PENDING" and now < deadline),
        items=[RebalancingPlanItemOut.model_validate(item) for item in leg.items],
    )


async def _get_owned_leg(
    plan_id: uuid.UUID, leg_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession
) -> RebalancingPlanLeg:
    leg = await db.scalar(
        select(RebalancingPlanLeg)
        .join(RebalancingPlan, RebalancingPlan.id == RebalancingPlanLeg.plan_id)
        .where(
            RebalancingPlanLeg.id == leg_id,
            RebalancingPlanLeg.plan_id == plan_id,
            RebalancingPlan.user_id == user_id,
        )
    )
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")
    return leg


@router.get("", response_model=list[RebalancingPlanLegSummary])
@limiter.limit("20/minute")
async def list_plans(
    request: Request,
    limit: int = 30,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 최근 대기중/종료된 리밸런싱 플랜 leg 목록 (EXECUTED는 실행 이력에서 확인)."""
    rows = await list_recent_plan_legs(current_user.id, db, limit=limit)
    return [_build_summary(leg, plan, name, acc_name) for leg, plan, name, acc_name in rows]


@router.post("/{plan_id}/legs/{leg_id}/cancel", response_model=PlanActionResponse)
@limiter.limit("10/minute")
async def cancel_plan_leg(
    request: Request,
    plan_id: uuid.UUID,
    leg_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대기중인 매수/매도 계획을 앱에서 취소한다."""
    leg = await _get_owned_leg(plan_id, leg_id, current_user.id, db)
    if leg.side == "BUY":
        await cancel_buy_leg(leg, db, decided_by="USER_APP")
        return PlanActionResponse(status="CANCELED", message="매수 대기가 취소되었습니다")
    await reject_sell_leg(leg, db, decided_by="USER_APP")
    return PlanActionResponse(status="REJECTED", message="매도 계획이 거부되었습니다")


@router.post("/{plan_id}/legs/{leg_id}/approve", response_model=PlanActionResponse)
@limiter.limit("5/minute")
async def approve_plan_leg(
    request: Request,
    plan_id: uuid.UUID,
    leg_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대기중인 매수/매도 계획을 앱에서 즉시 실행한다. 매수는 대기시간을 건너뛰고 바로 체결한다."""
    from app.redis_client import get_redis

    leg = await _get_owned_leg(plan_id, leg_id, current_user.id, db)
    redis = await get_redis()
    label = "매수" if leg.side == "BUY" else "매도"
    approve_fn = approve_buy_leg if leg.side == "BUY" else approve_sell_leg
    execution_id = await approve_fn(leg, db, redis, decided_by="USER_APP")
    if execution_id is None:
        return PlanActionResponse(status="FAILED", message=f"{label} 주문 실행에 실패했습니다")
    return PlanActionResponse(status="EXECUTED", message=f"{label} 주문이 실행되었습니다")
