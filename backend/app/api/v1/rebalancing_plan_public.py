"""리밸런싱 대기 플랜 토큰 기반 액션 — 인증 없음 (이메일 링크 전용).

이 파일에는 `Depends(get_current_user)`를 절대 사용하지 않는다 — 보안 경계를 파일 단위로
명확히 구분하기 위함. GET은 부작용 없이 미리보기만 제공하고(이메일 스캐너/프리페처가 클릭해도
안전), 실제 승인/취소는 반드시 POST로만 처리한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.limiter import limiter
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.schemas.rebalancing import (
    PlanActionResponse,
    PlanTokenPreview,
    RebalancingPlanItemOut,
    RebalancingPlanLegSummary,
    SellDecisionRequest,
)
from app.services.rebalancing_plan_service import (
    approve_sell_leg,
    cancel_buy_leg,
    get_plan_leg_by_token,
    reject_sell_leg,
)

router = APIRouter(prefix="/rebalancing/plan-actions", tags=["rebalancing-plan-public"])


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _build_preview(leg, db: AsyncSession) -> PlanTokenPreview:
    plan = leg.plan
    portfolio_name = None
    account_name = None
    if plan.portfolio_id:
        portfolio_name = await db.scalar(select(Portfolio.name).where(Portfolio.id == plan.portfolio_id))
    if plan.account_id:
        account_name = await db.scalar(select(AssetAccount.name).where(AssetAccount.id == plan.account_id))

    now = datetime.now(tz=UTC)
    if leg.status == "PENDING" and now >= _aware(leg.deadline_at):
        actionable, reason = False, "EXPIRED"
    elif leg.status == "PENDING":
        actionable, reason = True, None
    elif leg.status == "EXPIRED":
        actionable, reason = False, "EXPIRED"
    else:
        actionable, reason = False, "ALREADY_DECIDED"

    summary = RebalancingPlanLegSummary(
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
        actionable=actionable,
        items=[RebalancingPlanItemOut.model_validate(item) for item in leg.items],
    )
    return PlanTokenPreview(valid=True, reason=reason, actionable=actionable, leg=summary)


@router.get("/{token}", response_model=PlanTokenPreview)
@limiter.limit("20/minute")
async def preview_plan_action(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """토큰으로 계획을 미리보기한다. 읽기 전용 — DB를 변경하지 않는다."""
    leg = await get_plan_leg_by_token(token, None, db)
    if leg is None:
        return PlanTokenPreview(valid=False, reason="NOT_FOUND", actionable=False, leg=None)
    return await _build_preview(leg, db)


@router.post("/{token}/buy/cancel", response_model=PlanActionResponse)
@limiter.limit("10/minute")
async def cancel_buy_by_token(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """이메일 링크로 매수 대기를 취소한다."""
    leg = await get_plan_leg_by_token(token, "BUY", db)
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")
    await cancel_buy_leg(leg, db, decided_by="USER_EMAIL")
    return PlanActionResponse(status="CANCELED", message="매수 대기가 취소되었습니다")


@router.post("/{token}/sell/decision", response_model=PlanActionResponse)
@limiter.limit("5/minute")
async def decide_sell_by_token(
    request: Request,
    token: str,
    body: SellDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """이메일 링크로 매도 계획을 승인/거부한다. 승인 시 즉시 주문이 실행된다."""
    from app.redis_client import get_redis

    leg = await get_plan_leg_by_token(token, "SELL", db)
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")

    if body.decision == "REJECT":
        await reject_sell_leg(leg, db, decided_by="USER_EMAIL")
        return PlanActionResponse(status="REJECTED", message="매도 계획이 거부되었습니다")

    redis = await get_redis()
    execution_id = await approve_sell_leg(leg, db, redis, decided_by="USER_EMAIL")
    if execution_id is None:
        return PlanActionResponse(status="FAILED", message="주문 실행에 실패했습니다")
    return PlanActionResponse(status="EXECUTED", message="매도 주문이 실행되었습니다")
