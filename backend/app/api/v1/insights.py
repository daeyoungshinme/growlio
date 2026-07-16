"""스마트 인사이트 & 포트폴리오 진단 API."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.redis_client import get_redis
from app.limiter import limiter
from app.models.user import User
from app.services.insight_service import generate_insights

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("")
@limiter.limit("30/minute")
async def list_insights(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> list[dict]:
    """규칙 기반 포트폴리오 진단 인사이트 목록."""
    return await generate_insights(current_user.id, db, redis)
