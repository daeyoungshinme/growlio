"""목표환율 / 리밸런싱 알림 CRUD API."""
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
from app.models.alert import AlertHistory, ExchangeRateAlert, RebalancingAlert, StockPriceAlert
from app.models.portfolio import Portfolio
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
    return [AlertResponse.model_validate(a) for a in alerts]


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
    return AlertResponse.model_validate(alert)


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
    return AlertResponse.model_validate(alert)


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


# ── 리밸런싱 알림 ────────────────────────────────────────────────────────────


class RebalancingAlertCreate(BaseModel):
    portfolio_id: uuid.UUID
    threshold_pct: float = 5.0
    schedule_type: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"] = "DAILY"
    schedule_day_of_week: int | None = None  # WEEKLY 전용: 0=월...6=일
    schedule_day_of_month: int | None = None  # MONTHLY/QUARTERLY/SEMIANNUAL/ANNUAL: 1~28
    only_when_drift: bool = True
    mode: Literal["NOTIFY", "AUTO"] = "NOTIFY"
    strategy: Literal["FULL", "BUY_ONLY"] = "BUY_ONLY"
    account_id: uuid.UUID | None = None
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"

    @field_validator("threshold_pct")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not (0.1 <= v <= 50.0):
            raise ValueError("임계값은 0.1%에서 50% 사이여야 합니다")
        return round(v, 2)

    @field_validator("schedule_day_of_week")
    @classmethod
    def validate_dow(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 6):
            raise ValueError("요일은 0(월)~6(일) 사이여야 합니다")
        return v

    @field_validator("schedule_day_of_month")
    @classmethod
    def validate_dom(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 28):
            raise ValueError("날짜는 1~28 사이여야 합니다")
        return v


class RebalancingAlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    portfolio_id: uuid.UUID
    is_active: bool
    threshold_pct: float
    schedule_type: str
    schedule_day_of_week: int | None
    schedule_day_of_month: int | None
    only_when_drift: bool
    mode: str
    strategy: str
    account_id: uuid.UUID | None
    order_type: str
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


@router.get("/rebalancing", response_model=list[RebalancingAlertResponse])
async def list_rebalancing_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 리밸런싱 알림 목록 조회."""
    result = await db.execute(
        select(RebalancingAlert)
        .where(RebalancingAlert.user_id == current_user.id)
        .order_by(RebalancingAlert.created_at)
    )
    return result.scalars().all()


@router.get("/rebalancing/{portfolio_id}", response_model=RebalancingAlertResponse)
async def get_rebalancing_alert(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 리밸런싱 알림 설정 조회."""
    alert = await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == current_user.id,
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림이 설정되지 않았습니다")
    return alert


@router.put("/rebalancing/{portfolio_id}", response_model=RebalancingAlertResponse)
@limiter.limit("30/minute")
async def upsert_rebalancing_alert(
    request: Request,
    portfolio_id: uuid.UUID,
    body: RebalancingAlertCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 리밸런싱 알림 생성 또는 수정 (upsert)."""
    portfolio = await db.scalar(
        select(Portfolio).where(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
    )
    if not portfolio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="포트폴리오를 찾을 수 없습니다")

    alert = await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == current_user.id,
        )
    )
    if alert:
        alert.threshold_pct = body.threshold_pct
        alert.schedule_type = body.schedule_type
        alert.schedule_day_of_week = body.schedule_day_of_week
        alert.schedule_day_of_month = body.schedule_day_of_month
        alert.only_when_drift = body.only_when_drift
        alert.mode = body.mode
        alert.strategy = body.strategy
        alert.account_id = body.account_id
        alert.order_type = body.order_type
        alert.is_active = True
    else:
        alert = RebalancingAlert(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            threshold_pct=body.threshold_pct,
            schedule_type=body.schedule_type,
            schedule_day_of_week=body.schedule_day_of_week,
            schedule_day_of_month=body.schedule_day_of_month,
            only_when_drift=body.only_when_drift,
            mode=body.mode,
            strategy=body.strategy,
            account_id=body.account_id,
            order_type=body.order_type,
            is_active=True,
        )
        db.add(alert)

    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/rebalancing/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rebalancing_alert(
    portfolio_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """포트폴리오 리밸런싱 알림 삭제."""
    alert = await db.scalar(
        select(RebalancingAlert).where(
            RebalancingAlert.portfolio_id == portfolio_id,
            RebalancingAlert.user_id == current_user.id,
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다")
    await db.delete(alert)
    await db.commit()


# ── 주가 목표 알림 ────────────────────────────────────────────────────────────


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
async def list_stock_price_alerts(
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
async def reactivate_stock_price_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주가 알림 재활성화."""
    alert = await db.scalar(
        select(StockPriceAlert).where(
            StockPriceAlert.id == alert_id,
            StockPriceAlert.user_id == current_user.id,
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다")
    alert.is_active = True
    alert.trigger_count = 0
    await db.commit()
    await db.refresh(alert)
    return StockPriceAlertResponse.model_validate(alert)


@router.delete("/stock-price/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_stock_price_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """주가 알림 삭제."""
    alert = await db.scalar(
        select(StockPriceAlert).where(
            StockPriceAlert.id == alert_id,
            StockPriceAlert.user_id == current_user.id,
        )
    )
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="알림을 찾을 수 없습니다")
    await db.delete(alert)
    await db.commit()


class AlertHistoryItem(BaseModel):
    id: uuid.UUID
    alert_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/history", response_model=list[AlertHistoryItem])
@limiter.limit("30/minute")
async def list_alert_history(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 발송 이력 조회 (최신순)."""
    result = await db.execute(
        select(AlertHistory)
        .where(AlertHistory.user_id == current_user.id)
        .order_by(AlertHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()
