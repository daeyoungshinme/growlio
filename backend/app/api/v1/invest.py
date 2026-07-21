"""적립식 투자(DCA) 복리계산 및 목표달성율 API."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.redis_client import get_redis
from app.limiter import limiter
from app.models.user import User
from app.schemas.invest import DCAAnalysisResponse, DepositGuideItem, GoalFeasibilityPreview
from app.services import dca_service
from app.services.composition_calculator import build_asset_totals
from app.services.dividend import plan_service as dividend_plan_service
from app.services.goal_return_solver import (
    DEPOSIT_GUIDE_PRESET_RETURNS_PCT,
    months_until_year_end,
    solve_required_annual_return_pct,
    solve_required_monthly_deposit,
)

router = APIRouter(prefix="/invest", tags=["invest"])


@router.get("/dca-analysis", response_model=DCAAnalysisResponse)
@limiter.limit("60/minute")
async def get_dca_analysis(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """적립식 투자 복리계산 및 월/년 목표달성율 분석."""
    redis = await get_redis()
    result = await dca_service.get_dca_analysis(current_user.id, db, redis)
    return result


@router.get("/goal-feasibility", response_model=GoalFeasibilityPreview)
@limiter.limit("60/minute")
async def get_goal_feasibility(
    request: Request,
    goal_amount: float = Query(..., gt=0),
    target_year: int = Query(...),
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
        redis = await get_redis()
        pv, *_rest = await build_asset_totals(current_user.id, db, redis)

    n_months = months_until_year_end(target_year)
    if n_months <= 0:
        return GoalFeasibilityPreview(
            required_return_pct=None,
            pv=pv,
            n_months=n_months,
            note="목표 연도가 이미 지났습니다 — 목표연도를 다시 설정해주세요",
        )
    if pv >= goal_amount:
        return GoalFeasibilityPreview(
            required_return_pct=None, pv=pv, n_months=n_months, note="이미 목표 금액을 달성했습니다"
        )

    required_return_pct = solve_required_annual_return_pct(pv, monthly_deposit_amount, n_months, goal_amount)
    note = None if required_return_pct is not None else "현재 조건(적립액·기간)으로는 달성이 매우 어려운 목표입니다"
    deposit_guide = []
    for preset_pct in DEPOSIT_GUIDE_PRESET_RETURNS_PCT:
        monthly = solve_required_monthly_deposit(pv, preset_pct, n_months, goal_amount)
        deposit_guide.append(
            DepositGuideItem(
                annual_return_pct=preset_pct,
                required_monthly_deposit=monthly,
                required_annual_deposit=monthly * 12,
            )
        )
    return GoalFeasibilityPreview(
        required_return_pct=required_return_pct,
        pv=pv,
        n_months=n_months,
        note=note,
        deposit_guide=deposit_guide,
    )


@router.get("/dividend-plan")
@limiter.limit("60/minute")
async def get_dividend_plan(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """연배당/월배당 목표 달성 현황 및 월별·연도별 배당 분포."""
    redis = await get_redis()
    return await dividend_plan_service.get_dividend_plan(current_user.id, db, redis)
