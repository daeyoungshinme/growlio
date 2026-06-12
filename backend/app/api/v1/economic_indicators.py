"""경제지표 API — 미국 주요 경제지표 및 FRED 증시 캘린더 조회."""
from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.user import User
from app.redis_client import get_redis
from app.services.economic_calendar_service import get_calendar_events
from app.services.economic_indicator_service import (
    INDICATORS,
    _fred_get_observations,
    fetch_all_indicators,
    fetch_indicator_history,
    get_user_subscriptions,
    subscribe_indicator,
    unsubscribe_indicator,
)

router = APIRouter(prefix="/economic-indicators", tags=["economic_indicators"])
logger = structlog.get_logger()


@router.get("/health")
@limiter.limit("10/minute")
async def check_health(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """FRED API 연결 상태를 진단한다."""
    from app.config import settings

    fred_configured = bool(settings.fred_api_key)
    if fred_configured:
        obs = await _fred_get_observations("CPIAUCSL", limit=1)
        fred_status = {
            "configured": True,
            "status": "ok" if obs else "error",
            "detail": None if obs else "데이터를 가져오지 못했습니다. 백엔드 로그를 확인하세요.",
        }
    else:
        fred_status = {
            "configured": False,
            "status": "not_configured",
            "detail": "FRED_API_KEY가 설정되지 않았습니다.",
        }

    return {"fred": fred_status}


@router.get("")
@limiter.limit("30/minute")
async def list_indicators(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """미국 주요 경제지표 최신값 목록을 반환한다."""
    redis = await get_redis()
    indicators, subscriptions = await _gather_indicators_and_subs(current_user, db, redis)
    for item in indicators:
        item["subscribed"] = item["code"] in subscriptions
    return indicators


@router.get("/calendar")
@limiter.limit("20/minute")
async def get_calendar(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """향후 90일 내 발표 예정 경제 이벤트 일정을 반환한다 (FRED 기반)."""
    redis = await get_redis()
    return await get_calendar_events(redis)


@router.get("/subscriptions")
@limiter.limit("30/minute")
async def list_subscriptions(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내가 구독 중인 경제지표 코드 목록을 반환한다."""
    return await get_user_subscriptions(current_user.id, db)


@router.post("/{code}/subscribe", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def subscribe(
    request: Request,
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """경제지표 알림 구독을 추가한다."""
    if code not in INDICATORS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"지원하지 않는 지표 코드입니다: {code}",
        )
    await subscribe_indicator(current_user.id, code, db)
    logger.info("indicator_subscribed", user_id=str(current_user.id), code=code)


@router.delete("/{code}/subscribe", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def unsubscribe(
    request: Request,
    code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """경제지표 알림 구독을 해제한다."""
    await unsubscribe_indicator(current_user.id, code, db)
    logger.info("indicator_unsubscribed", user_id=str(current_user.id), code=code)


@router.get("/{code}/history")
@limiter.limit("20/minute")
async def get_history(
    request: Request,
    code: str,
    months: int = Query(default=24, ge=3, le=60),
    current_user: User = Depends(get_current_user),
):
    """특정 경제지표의 최근 N개월 시계열 데이터를 반환한다."""
    if code not in INDICATORS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"지원하지 않는 지표 코드입니다: {code}",
        )
    redis = await get_redis()
    return await fetch_indicator_history(code, months, redis)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _gather_indicators_and_subs(user: User, db: AsyncSession, redis) -> tuple[list, set[str]]:
    """지표 목록과 구독 목록을 병렬로 조회한다."""
    import asyncio

    indicators_task = fetch_all_indicators(redis)
    subs_task = get_user_subscriptions(user.id, db)
    indicators, subs = await asyncio.gather(indicators_task, subs_task, return_exceptions=True)
    if isinstance(indicators, Exception):
        indicators = []
    if isinstance(subs, Exception):
        subs = []
    return indicators, set(subs)
