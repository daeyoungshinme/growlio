"""목표환율 알림 CRUD API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.alert import ExchangeRateAlert
from app.models.user import User

router = APIRouter(prefix="/alerts", tags=["alerts"])


class AlertCreate(BaseModel):
    target_rate: float
    direction: Literal["BELOW", "ABOVE"]

    @field_validator("target_rate")
    @classmethod
    def validate_rate(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("목표환율은 0보다 커야 합니다")
        return v


class AlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    target_rate: float
    direction: str
    is_active: bool
    triggered_at: datetime | None
    created_at: datetime

    @classmethod
    def from_orm_row(cls, row: ExchangeRateAlert) -> "AlertResponse":
        return cls(
            id=row.id,
            target_rate=float(row.target_rate),
            direction=row.direction,
            is_active=row.is_active,
            triggered_at=row.triggered_at,
            created_at=row.created_at,
        )


@router.get("/exchange-rate", response_model=list[AlertResponse])
async def list_exchange_rate_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 목표환율 알림 목록 조회 (활성 + 발동 이력)."""
    result = await db.execute(
        select(ExchangeRateAlert)
        .where(ExchangeRateAlert.user_id == current_user.id)
        .order_by(ExchangeRateAlert.created_at.desc())
    )
    alerts = result.scalars().all()
    return [AlertResponse.from_orm_row(a) for a in alerts]


@router.post("/exchange-rate", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_exchange_rate_alert(
    req: AlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표환율 알림 생성."""
    alert = ExchangeRateAlert(
        user_id=current_user.id,
        target_rate=req.target_rate,
        direction=req.direction,
    )
    db.add(alert)
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
