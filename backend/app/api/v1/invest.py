"""적립식 투자(DCA) 복리계산 및 목표달성율 API."""

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.fx_extra_need import FxExtraNeed
from app.models.user import User
from app.schemas.invest import (
    DCAAnalysisResponse,
    FxExtraNeedCreate,
    FxExtraNeedResponse,
    FxExtraNeedsResponse,
    FxExtraNeedUpdate,
    FxPlanAlertSyncRequest,
    FxPlanAlertSyncResponse,
    FxPlanAlertTargets,
    FxPlanResponse,
    GoalFeasibilityPreview,
)
from app.services import dca_service, fx_extra_need_service, fx_plan_service
from app.services.dividend import plan_service as dividend_plan_service
from app.services.goal.goal_return_solver import build_feasibility_preview, months_until_year_end
from app.services.portfolio.composition_calculator import build_asset_totals, exclude_real_estate
from app.utils.cache_invalidation import invalidate_exchange_rate_alert_caches
from app.utils.kst import today_kst

router = APIRouter(prefix="/invest", tags=["invest"])


@router.get("/dca-analysis", response_model=DCAAnalysisResponse)
@limiter.limit("60/minute")
async def get_dca_analysis(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """적립식 투자 복리계산 및 월/년 목표달성율 분석."""
    cache = await get_cache_store()
    result = await dca_service.get_dca_analysis(current_user.id, db, cache)
    return result


@router.get("/goal-feasibility", response_model=GoalFeasibilityPreview)
@limiter.limit("60/minute")
async def get_goal_feasibility(
    request: Request,
    goal_amount: float = Query(..., gt=0),
    target_year: int = Query(..., ge=2000, le=2200),
    monthly_deposit_amount: float = Query(0, ge=0),
    initial_amount: float | None = Query(None, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표금액·목표연도로부터 (1) 입력한 월적립액 기준 필요 연평균 수익률과 (2) 가정 수익률
    프리셋별 필요 월/연 적립액을 함께 역산한다.

    아무것도 저장하지 않는 미리보기 전용 엔드포인트 — 목표 설정 마법사(3/4 월 적립액, 4/4 결과
    확인 단계)가 사용. (2)는 monthly_deposit_amount와 무관하게 계산되므로 아직 적립액을
    정하지 못한 3단계에서도 바로 가이드로 사용할 수 있다.
    """
    if initial_amount is not None:
        pv = initial_amount
    else:
        cache = await get_cache_store()
        total_assets_krw, _, _, by_type = await build_asset_totals(current_user.id, db, cache)
        pv = exclude_real_estate(total_assets_krw, by_type)

    n_months = months_until_year_end(target_year)
    return build_feasibility_preview(
        pv,
        goal_amount,
        n_months,
        monthly_deposit_amount,
        expired_note="목표 연도가 이미 지났습니다 — 목표연도를 다시 설정해주세요",
    )


@router.get("/dividend-plan")
@limiter.limit("60/minute")
async def get_dividend_plan(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """연배당/월배당 목표 달성 현황 및 월별·연도별 배당 분포."""
    cache = await get_cache_store()
    return await dividend_plan_service.get_dividend_plan(current_user.id, db, cache)


@router.get("/fx-plan", response_model=FxPlanResponse)
@limiter.limit("30/minute")
async def get_fx_plan(
    request: Request,
    portfolio_id: uuid.UUID | None = Query(None),
    months: int = Query(3, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """환율 1년 위치·범위 + 해외 적립에 필요한 달러의 분할 환전 계획(저장 없음, 예측 아님)."""
    cache = await get_cache_store()
    return await fx_plan_service.get_fx_plan(db, cache, current_user.id, portfolio_id, months)


@router.put("/fx-plan/alerts", response_model=FxPlanAlertSyncResponse)
@limiter.limit("20/minute")
async def sync_fx_plan_alerts(
    request: Request,
    req: FxPlanAlertSyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """환전 계획 구간 목표로 환율 알림을 맞춘다 — 새 목표는 만들고, 빠진 미발동 계획 알림은 지운다(plans/121)."""
    cache = await get_cache_store()
    result = await fx_plan_service.sync_fx_plan_alerts(
        db,
        cache,
        current_user.id,
        req.portfolio_id,
        [(t.target_rate, t.usd) for t in req.targets],
    )
    await invalidate_exchange_rate_alert_caches(cache, current_user.id)
    return FxPlanAlertSyncResponse(**asdict(result))


# ── 추가 환전 항목(여행 등, plans/123) ─────────────────────────


async def _need_row(db: AsyncSession, need: FxExtraNeed) -> FxExtraNeedResponse:
    """생성·수정 응답 한 행 — 목록과 같은 규칙으로 구간까지 계산한다."""
    cache = await get_cache_store()
    ctx = await fx_plan_service.load_fx_rate_context(cache)
    account_name = await fx_extra_need_service.reserved_account_name(db, need)
    return FxExtraNeedResponse(
        **fx_extra_need_service.build_need_row(need, ctx.position, ctx.rate, ctx.has_rate, today_kst(), account_name)
    )


@router.get("/fx-extra-needs", response_model=FxExtraNeedsResponse)
@limiter.limit("30/minute")
async def list_fx_extra_needs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """추가 환전 항목(여행 등)과 항목별 분할 환전 구간 — 증권 계좌 달러로 상쇄하지 않는다."""
    cache = await get_cache_store()
    return await fx_extra_need_service.list_fx_extra_needs(db, cache, current_user.id)


@router.post("/fx-extra-needs", response_model=FxExtraNeedResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_fx_extra_need(
    request: Request,
    req: FxExtraNeedCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    need = await fx_extra_need_service.create_fx_extra_need(
        db,
        current_user.id,
        req.name,
        req.amount_usd,
        req.exchanged_usd,
        req.due_date,
        reserved_account_id=req.reserved_account_id,
    )
    return await _need_row(db, need)


@router.patch("/fx-extra-needs/{need_id}", response_model=FxExtraNeedResponse)
@limiter.limit("30/minute")
async def update_fx_extra_need(
    request: Request,
    need_id: uuid.UUID,
    req: FxExtraNeedUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # null은 무시하되 보관 계좌의 null은 "계좌 밖"으로 해제하는 값이다
    changes = {
        k: v
        for k, v in req.model_dump(include=req.model_fields_set).items()
        if v is not None or k == "reserved_account_id"
    }
    need = await fx_extra_need_service.update_fx_extra_need(db, current_user.id, need_id, changes)
    return await _need_row(db, need)


@router.delete("/fx-extra-needs/{need_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_fx_extra_need(
    request: Request,
    need_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """항목과 그 구간 알림을 함께 지운다."""
    await fx_extra_need_service.delete_fx_extra_need(db, current_user.id, need_id)
    cache = await get_cache_store()
    await invalidate_exchange_rate_alert_caches(cache, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/fx-extra-needs/{need_id}/alerts", response_model=FxPlanAlertSyncResponse)
@limiter.limit("20/minute")
async def sync_fx_extra_need_alerts(
    request: Request,
    need_id: uuid.UUID,
    req: FxPlanAlertTargets,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """추가 환전 항목의 구간 목표로 환율 알림을 맞춘다 — 적립 계획 알림은 건드리지 않는다."""
    cache = await get_cache_store()
    result = await fx_plan_service.sync_fx_plan_alerts(
        db,
        cache,
        current_user.id,
        None,
        [(t.target_rate, t.usd) for t in req.targets],
        fx_need_id=need_id,
    )
    await invalidate_exchange_rate_alert_caches(cache, current_user.id)
    return FxPlanAlertSyncResponse(**asdict(result))
