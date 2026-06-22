"""주가 목표 알림 CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1._account_deps import get_owned_or_404
from app.database import get_db
from app.limiter import limiter
from app.models.alert import StockPriceAlert
from app.models.user import User

router = APIRouter()


class StockPriceAlertCreate(BaseModel):
    ticker: str
    market: str
    name: str
    target_price: float
    direction: Literal["BELOW", "ABOVE"]
    max_trigger_count: int = 1

    @field_validator("target_price")
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("목표가는 0보다 커야 합니다")
        return v

    @field_validator("max_trigger_count")
    @classmethod
    def validate_count(cls, v: int) -> int:
        if v < 1:
            raise ValueError("알림 횟수는 1 이상이어야 합니다")
        return v


class StockPriceAlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    ticker: str
    market: str
    name: str
    target_price: float
    direction: str
    is_active: bool
    max_trigger_count: int
    trigger_count: int
    triggered_at: datetime | None
    created_at: datetime


@router.get("/stock-price", response_model=list[StockPriceAlertResponse])
@limiter.limit("30/minute")
async def list_stock_price_alerts(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 200,
):
    """주가 목표 알림 목록 조회."""
    result = await db.execute(
        select(StockPriceAlert)
        .where(StockPriceAlert.user_id == current_user.id)
        .order_by(StockPriceAlert.created_at.desc())
        .offset(skip)
        .limit(min(limit, 500))
    )
    return [StockPriceAlertResponse.model_validate(a) for a in result.scalars().all()]


@router.post("/stock-price", response_model=StockPriceAlertResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_stock_price_alert(
    request: Request,
    req: StockPriceAlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주가 목표 알림 생성."""
    alert = StockPriceAlert(
        user_id=current_user.id,
        ticker=req.ticker,
        market=req.market,
        name=req.name,
        target_price=req.target_price,
        direction=req.direction,
        max_trigger_count=req.max_trigger_count,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return StockPriceAlertResponse.model_validate(alert)


@router.patch("/stock-price/{alert_id}/reactivate", response_model=StockPriceAlertResponse)
@limiter.limit("20/minute")
async def reactivate_stock_price_alert(
    request: Request,
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주가 알림 재활성화."""
    alert = await get_owned_or_404(db, StockPriceAlert, alert_id, current_user.id, "알림을 찾을 수 없습니다")
    alert.is_active = True
    alert.trigger_count = 0
    await db.commit()
    await db.refresh(alert)
    return StockPriceAlertResponse.model_validate(alert)


@router.delete("/stock-price/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_stock_price_alert(
    request: Request,
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주가 알림 삭제."""
    alert = await get_owned_or_404(db, StockPriceAlert, alert_id, current_user.id, "알림을 찾을 수 없습니다")
    await db.delete(alert)
    await db.commit()
