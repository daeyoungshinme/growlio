"""경제지표 API — CPI/Core CPI 인플레이션 요약 조회."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.deps import get_current_user
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.user import User
from app.services.economic_indicator_service import fetch_inflation_summary

router = APIRouter(prefix="/economic-indicators", tags=["economic_indicators"])


@router.get("/inflation-summary")
@limiter.limit("30/minute")
async def get_inflation_summary(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """CPI·Core CPI 최신값과 전월/전년 대비 변화율, 다음 발표일을 요약해 반환한다 (리밸런싱 참고용)."""
    cache = await get_cache_store()
    return await fetch_inflation_summary(cache)
