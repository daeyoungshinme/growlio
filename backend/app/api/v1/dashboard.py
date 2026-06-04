from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.asset import DashboardResponse
from app.services.asset_aggregator import get_benchmark_comparison, get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_VALID_INDICES = {"KOSPI", "SP500", "NASDAQ"}


@router.get("", response_model=DashboardResponse)
@limiter.limit("10/minute")
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    return await get_dashboard_summary(current_user.id, db, redis)


@router.get("/benchmark")
@limiter.limit("10/minute")
async def benchmark(
    request: Request,
    indices: Annotated[str, Query(description="쉼표구분 지수 코드")] = "KOSPI,SP500",
    months: Annotated[int, Query(ge=1, le=24)] = 12,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """월별 내 자산 vs 벤치마크 누적 수익률 비교."""
    requested = [
        i.strip().upper() for i in indices.split(",") if i.strip().upper() in _VALID_INDICES
    ]
    redis = await get_redis()
    return await get_benchmark_comparison(current_user.id, months, requested, db, redis)
