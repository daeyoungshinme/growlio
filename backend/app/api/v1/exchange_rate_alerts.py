"""목표환율 알림 CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._account_deps import get_owned_or_404
from app.limiter import limiter
from app.models.alert import ExchangeRateAlert
from app.models.user import User
from app.redis_client import get_redis
from app.utils.cache_keys import (
    TTL_EXCHANGE_RATE_ALERTS,
    exchange_rate_alerts_key,
    get_cached_json,
    invalidate_exchange_rate_alert_caches,
    set_cached_json,
)

router = APIRouter()


class AlertCreate(BaseModel):
    target_rate: float
    direction: Literal["BELOW", "ABOVE"]
    max_trigger_count: int = 1

    @field_validator("target_rate")
    @classmethod
    def validate_rate(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("목표환율은 0보다 커야 합니다")
        return v

    @field_validator("max_trigger_count")
    @classmethod
    def validate_count(cls, v: int) -> int:
        if v < 1:
            raise ValueError("알림 횟수는 1 이상이어야 합니다")
        return v


class AlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    target_rate: float
    direction: str
    is_active: bool
    max_trigger_count: int
    trigger_count: int
    triggered_at: datetime | None
    created_at: datetime


@router.get("/exchange-rate", response_model=list[AlertResponse])
@limiter.limit("30/minute")
async def list_exchange_rate_alerts(
    request: Request,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 목표환율 알림 목록 조회 (활성 + 발동 이력)."""
    redis = await get_redis()
    cache_key = exchange_rate_alerts_key(current_user.id)
    if skip == 0 and limit == 50:
        cached = await get_cached_json(redis, cache_key)
        if cached is not None:
            return cached

    result = await db.execute(
        select(ExchangeRateAlert)
        .where(ExchangeRateAlert.user_id == current_user.id)
        .order_by(ExchangeRateAlert.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    alerts_list = [AlertResponse.model_validate(a) for a in result.scalars().all()]

    if skip == 0 and limit == 50:
        payload = [a.model_dump(mode="json") for a in alerts_list]
        await set_cached_json(redis, cache_key, payload, TTL_EXCHANGE_RATE_ALERTS)
    return alerts_list


@router.post("/exchange-rate", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_exchange_rate_alert(
    request: Request,
    req: AlertCreate,
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
    await invalidate_exchange_rate_alert_caches(await get_redis(), current_user.id)
    return AlertResponse.model_validate(alert)


@router.patch("/exchange-rate/{alert_id}/reactivate", response_model=AlertResponse)
async def reactivate_exchange_rate_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """비활성 알림을 재활성화하고 발동 횟수를 초기화한다."""
    alert = await get_owned_or_404(db, ExchangeRateAlert, alert_id, current_user.id, "알림을 찾을 수 없습니다")
    alert.is_active = True
    alert.trigger_count = 0
    await db.commit()
    await db.refresh(alert)
    await invalidate_exchange_rate_alert_caches(await get_redis(), current_user.id)
    return AlertResponse.model_validate(alert)


@router.delete("/exchange-rate/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exchange_rate_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표환율 알림 삭제."""
    alert = await get_owned_or_404(db, ExchangeRateAlert, alert_id, current_user.id, "알림을 찾을 수 없습니다")
    await db.delete(alert)
    await db.commit()
    await invalidate_exchange_rate_alert_caches(await get_redis(), current_user.id)
