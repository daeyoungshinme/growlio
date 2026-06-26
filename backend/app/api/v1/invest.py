"""적립식 투자(DCA) 복리계산 및 목표달성율 API."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.invest import DCAAnalysisResponse
from app.services import dca_service, dividend_plan_service

router = APIRouter(prefix="/invest", tags=["invest"])


@router.get("/dca-analysis", response_model=DCAAnalysisResponse)
@limiter.limit("60/minute")
async def get_dca_analysis(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """적립식 투자 복리계산 및 월/년 목표달성율 분석."""
    result = await dca_service.get_dca_analysis(current_user.id, db)
    return result


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
