"""DART OpenAPI — 보유 종목 공시 목록 조회."""

from __future__ import annotations

import contextlib
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.asset import AssetAccount, Position
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.credential_service import decrypt
from app.services.dart_service import fetch_disclosures_for_tickers
from app.utils.cache_keys import TTL_DART, dart_disclosures_key

router = APIRouter(prefix="/dart", tags=["dart"])
logger = structlog.get_logger()

_DOMESTIC_MARKETS = frozenset({"KOSPI", "KOSDAQ"})


@router.get("/disclosures")
@limiter.limit("10/minute")
async def get_disclosures(
    request: Request,
    days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """보유 국내 주식 종목의 최근 DART 공시 목록을 반환한다."""
    settings_row = await db.scalar(select(UserSettings).where(UserSettings.user_id == current_user.id))
    if not settings_row or not settings_row.dart_api_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DART API 키가 설정되지 않았습니다.",
        )
    try:
        api_key = decrypt(settings_row.dart_api_key)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DART API 키 복호화에 실패했습니다. 키를 다시 설정해주세요.",
        ) from None

    redis = await get_redis()
    cache_key = dart_disclosures_key(current_user.id, days)
    try:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except (RedisError, json.JSONDecodeError) as e:
        logger.warning("dart_cache_read_failed", error=str(e))

    result = await db.execute(
        select(Position.ticker)
        .join(AssetAccount, AssetAccount.id == Position.account_id)
        .where(
            AssetAccount.user_id == current_user.id,
            AssetAccount.is_active == True,  # noqa: E712
            Position.snapshot_id == None,  # noqa: E711
            Position.market.in_(_DOMESTIC_MARKETS),
        )
        .distinct()
    )
    tickers = [row[0] for row in result.all()]

    if not tickers:
        return []

    items = await fetch_disclosures_for_tickers(tickers, api_key, days=days)

    with contextlib.suppress(RedisError):
        await redis.set(cache_key, json.dumps(items, ensure_ascii=False), ex=TTL_DART)

    return items
