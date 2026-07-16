from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.redis_client import get_redis
from app.limiter import limiter
from app.models.user import User
from app.schemas.asset import DashboardResponse
from app.services.asset_aggregator import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
@limiter.limit("10/minute")
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    return await get_dashboard_summary(current_user.id, db, redis)
