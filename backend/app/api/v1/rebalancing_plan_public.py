"""리밸런싱 대기 플랜 토큰 기반 액션 — 인증 없음 (이메일 링크 전용).

이 파일에는 `Depends(get_current_user)`를 절대 사용하지 않는다 — 보안 경계를 파일 단위로
명확히 구분하기 위함. GET은 부작용 없이 미리보기만 제공하고(이메일 스캐너/프리페처가 클릭해도
안전), 실제 승인/취소는 반드시 POST로만 처리한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.limiter import ip_rate_limit_key, limiter, peer_rate_limit_key
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.schemas.rebalancing import (
    PlanActionResponse,
    PlanTokenPreview,
    SellDecisionRequest,
)
from app.services.rebalancing.plan_execution import leg_executed_message
from app.services.rebalancing.plan_service import (
    approve_sell_leg,
    build_leg_summary,
    cancel_buy_leg,
    get_plan_leg_by_token,
    reject_sell_leg,
)

router = APIRouter(prefix="/rebalancing/plan-actions", tags=["rebalancing-plan-public"])


async def _build_preview(leg, db: AsyncSession) -> PlanTokenPreview:
    plan = leg.plan
    portfolio_name = None
    account_name = None
    if plan.portfolio_id:
        portfolio_name = await db.scalar(select(Portfolio.name).where(Portfolio.id == plan.portfolio_id))
    if plan.account_id:
        account_name = await db.scalar(select(AssetAccount.name).where(AssetAccount.id == plan.account_id))

    summary = build_leg_summary(leg, plan, portfolio_name, account_name)
    if summary.actionable:
        reason = None
    elif leg.status in ("PENDING", "EXPIRED"):
        reason = "EXPIRED"
    else:
        reason = "ALREADY_DECIDED"
    return PlanTokenPreview(valid=True, reason=reason, actionable=summary.actionable, leg=summary)


@router.get("/{token}", response_model=PlanTokenPreview)
@limiter.limit("20/minute", key_func=ip_rate_limit_key)
@limiter.limit("200/minute", key_func=peer_rate_limit_key)
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
@limiter.limit("10/minute", key_func=ip_rate_limit_key)
@limiter.limit("100/minute", key_func=peer_rate_limit_key)
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
@limiter.limit("5/minute", key_func=ip_rate_limit_key)
@limiter.limit("50/minute", key_func=peer_rate_limit_key)
async def decide_sell_by_token(
    request: Request,
    token: str,
    body: SellDecisionRequest,
    db: AsyncSession = Depends(get_db),
):
    """이메일 링크로 매도 계획을 승인/거부한다. 승인 시 즉시 주문이 실행된다."""
    from app.core.cache_store import get_cache_store

    leg = await get_plan_leg_by_token(token, "SELL", db)
    if leg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계획을 찾을 수 없습니다")

    if body.decision == "REJECT":
        await reject_sell_leg(leg, db, decided_by="USER_EMAIL")
        return PlanActionResponse(status="REJECTED", message="매도 계획이 거부되었습니다")

    cache = await get_cache_store()
    execution_id = await approve_sell_leg(leg, db, cache, decided_by="USER_EMAIL")
    # 실행 기록 저장만 실패한 경우 execution_id는 없지만 주문은 나갔다 — leg 상태로 판정(plans/62 A7)
    if execution_id is None and leg.status != "EXECUTED":
        return PlanActionResponse(status="FAILED", message="주문 실행에 실패했습니다")
    return PlanActionResponse(status="EXECUTED", message=leg_executed_message("매도", execution_id))
