"""목표환율 알림 CRUD."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._alert_crud import register_alert_reactivate_delete
from app.core.cache_store import get_cache_store
from app.limiter import limiter
from app.models.alert import ExchangeRateAlert
from app.models.user import User
from app.schemas.alert import ExchangeRateAlertCreate, ExchangeRateAlertResponse
from app.utils.cache_keys import (
    TTL_EXCHANGE_RATE_ALERTS,
    exchange_rate_alerts_key,
    get_cached_json,
    invalidate_exchange_rate_alert_caches,
    set_cached_json,
)

router = APIRouter()


@router.get("/exchange-rate", response_model=list[ExchangeRateAlertResponse])
@limiter.limit("30/minute")
async def list_exchange_rate_alerts(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 목표환율 알림 목록 조회 (활성 + 발동 이력)."""
    cache = await get_cache_store()
    cache_key = exchange_rate_alerts_key(current_user.id)
    if skip == 0 and limit == 50:
        cached = await get_cached_json(cache, cache_key)
        if cached is not None:
            return cached

    result = await db.execute(
        select(ExchangeRateAlert)
        .where(ExchangeRateAlert.user_id == current_user.id)
        .order_by(ExchangeRateAlert.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    alerts_list = [ExchangeRateAlertResponse.model_validate(a) for a in result.scalars().all()]

    if skip == 0 and limit == 50:
        payload = [a.model_dump(mode="json") for a in alerts_list]
        await set_cached_json(cache, cache_key, payload, TTL_EXCHANGE_RATE_ALERTS)
    return alerts_list


@router.post("/exchange-rate", response_model=ExchangeRateAlertResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_exchange_rate_alert(
    request: Request,
    req: ExchangeRateAlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표환율 알림 생성."""
    alert = ExchangeRateAlert(
        user_id=current_user.id,
        target_rate=req.target_rate,
        direction=req.direction,
        max_trigger_count=req.max_trigger_count,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    await invalidate_exchange_rate_alert_caches(await get_cache_store(), current_user.id)
    return ExchangeRateAlertResponse.model_validate(alert)


async def _invalidate_exchange_rate_caches(user_id: uuid.UUID) -> None:
    await invalidate_exchange_rate_alert_caches(await get_cache_store(), user_id)


register_alert_reactivate_delete(
    router,
    path_prefix="/exchange-rate",
    model=ExchangeRateAlert,
    response_model=ExchangeRateAlertResponse,
    invalidate_cache=_invalidate_exchange_rate_caches,
)
