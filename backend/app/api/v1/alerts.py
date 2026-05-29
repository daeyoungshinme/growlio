"""목표환율 알림 CRUD API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.limiter import limiter
from app.models.alert import ExchangeRateAlert
from app.models.user import User

router = APIRouter(prefix="/alerts", tags=["alerts"])


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

    @classmethod
    def from_orm_row(cls, row: ExchangeRateAlert) -> AlertResponse:
        return cls(
            id=row.id,
            target_rate=float(row.target_rate),
            direction=row.direction,
            is_active=row.is_active,
            max_trigger_count=row.max_trigger_count,
            trigger_count=row.trigger_count,
            triggered_at=row.triggered_at,
            created_at=row.created_at,
        )


@router.get("/exchange-rate", response_model=list[AlertResponse])
async def list_exchange_rate_alerts(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 목표환율 알림 목록 조회 (활성 + 발동 이력)."""
    result = await db.execute(
        select(ExchangeRateAlert)
        .where(ExchangeRateAlert.user_id == current_user.id)
        .order_by(ExchangeRateAlert.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    alerts = result.scalars().all()
    return [AlertResponse.from_orm_row(a) for a in alerts]


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
    return AlertResponse.from_orm_row(alert)


@router.patch("/exchange-rate/{alert_id}/reactivate", response_model=AlertResponse)
async def reactivate_exchange_rate_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """비활성 알림을 재활성화하고 발동 횟수를 초기화한다."""
    alert = await db.scalar(
        select(ExchangeRateAlert).where(
            ExchangeRateAlert.id == alert_id,
            ExchangeRateAlert.user_id == current_user.id,
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다")
    alert.is_active = True
    alert.trigger_count = 0
    await db.commit()
    await db.refresh(alert)
    return AlertResponse.from_orm_row(alert)


@router.delete("/exchange-rate/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exchange_rate_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표환율 알림 삭제."""
    alert = await db.scalar(
        select(ExchangeRateAlert).where(
            ExchangeRateAlert.id == alert_id,
            ExchangeRateAlert.user_id == current_user.id,
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다")
    await db.delete(alert)
    await db.commit()
