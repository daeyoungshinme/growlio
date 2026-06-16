"""리밸런싱 알림 CRUD."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.v1._account_deps import get_owned_or_404
from app.database import get_db
from app.limiter import limiter
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User

router = APIRouter()


class RebalancingAlertCreate(BaseModel):
    portfolio_id: uuid.UUID
    threshold_pct: float = 5.0
    schedule_type: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"] = "DAILY"
    schedule_day_of_week: int | None = None  # WEEKLY 전용: 0=월...6=일
    schedule_day_of_month: int | None = None  # MONTHLY/QUARTERLY/SEMIANNUAL/ANNUAL: 1~28
    trigger_condition: Literal["DRIFT_ONLY", "SCHEDULE_ONLY", "BOTH"] = "DRIFT_ONLY"
    mode: Literal["NOTIFY", "AUTO"] = "NOTIFY"
    strategy: Literal["FULL", "BUY_ONLY"] = "BUY_ONLY"
    account_id: uuid.UUID | None = None
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    market_condition_mode: Literal["DISABLED", "CAUTIOUS", "STRICT"] = "DISABLED"
    deposit_trigger_enabled: bool = False
    deposit_trigger_account_id: uuid.UUID | None = None
    deposit_trigger_min_amount_krw: int | None = None

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

    @field_validator("deposit_trigger_min_amount_krw")
    @classmethod
    def validate_min_amount(cls, v: int | None) -> int | None:
        if v is not None and v < 10_000:
            raise ValueError("최소 감지 금액은 10,000원 이상이어야 합니다")
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
    trigger_condition: str
    mode: str
    strategy: str
    account_id: uuid.UUID | None
    order_type: str
    market_condition_mode: str
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime
    deposit_trigger_enabled: bool
    deposit_trigger_account_id: uuid.UUID | None
    deposit_trigger_min_amount_krw: int | None
    last_known_deposit_krw: float | None
    last_deposit_checked_at: datetime | None


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
    await get_owned_or_404(db, Portfolio, portfolio_id, current_user.id, "포트폴리오를 찾을 수 없습니다")

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
        alert.trigger_condition = body.trigger_condition
        alert.mode = body.mode
        alert.strategy = body.strategy
        alert.account_id = body.account_id
        alert.order_type = body.order_type
        alert.market_condition_mode = body.market_condition_mode
        alert.is_active = True
        alert.deposit_trigger_enabled = body.deposit_trigger_enabled
        alert.deposit_trigger_account_id = body.deposit_trigger_account_id
        alert.deposit_trigger_min_amount_krw = body.deposit_trigger_min_amount_krw
    else:
        alert = RebalancingAlert(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            threshold_pct=body.threshold_pct,
            schedule_type=body.schedule_type,
            schedule_day_of_week=body.schedule_day_of_week,
            schedule_day_of_month=body.schedule_day_of_month,
            trigger_condition=body.trigger_condition,
            mode=body.mode,
            strategy=body.strategy,
            account_id=body.account_id,
            order_type=body.order_type,
            market_condition_mode=body.market_condition_mode,
            is_active=True,
            deposit_trigger_enabled=body.deposit_trigger_enabled,
            deposit_trigger_account_id=body.deposit_trigger_account_id,
            deposit_trigger_min_amount_krw=body.deposit_trigger_min_amount_krw,
        )
        db.add(alert)

    # 예수금 입금 감지 활성화 시 기준 예수금 초기화 (첫 발동 즉시 트리거 방지)
    if body.deposit_trigger_enabled and body.deposit_trigger_account_id:
        trigger_account = await db.scalar(
            select(AssetAccount).where(
                AssetAccount.id == body.deposit_trigger_account_id,
                AssetAccount.user_id == current_user.id,
            )
        )
        if trigger_account and trigger_account.deposit_krw is not None:
            alert.last_known_deposit_krw = trigger_account.deposit_krw

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
