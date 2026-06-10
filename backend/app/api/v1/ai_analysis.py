"""AI 시황 분석 및 포트폴리오 추천 API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.ai_analysis import AIAnalysisResponse
from app.services.ai_analysis_service import get_ai_analysis

router = APIRouter(prefix="/ai-analysis", tags=["ai-analysis"])


@router.get("", response_model=AIAnalysisResponse)
@limiter.limit("5/minute")
async def get_analysis(
    request: Request,
    force_refresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 시황 분석 및 포트폴리오 추천. Redis TTL 1시간 캐시."""
    redis = await get_redis()
    return await get_ai_analysis(current_user.id, db, redis, force_refresh=force_refresh)
