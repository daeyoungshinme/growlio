"""리밸런싱 알림 CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._account_deps import get_owned_or_404
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
    strategy: Literal["FULL", "BUY_ONLY", "TWO_PHASE"] = "BUY_ONLY"
    account_id: uuid.UUID | None = None
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    market_condition_mode: Literal["DISABLED", "CAUTIOUS", "STRICT"] = "DISABLED"
    # AUTO 모드 실행 시각 (HH:MM KST, 예: "09:30"). None이면 장 개시 후 첫 tick에 실행
    auto_execution_time: str | None = None

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

    @field_validator("auto_execution_time")
    @classmethod
    def validate_auto_execution_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            hh, mm = v.split(":")
            hour, minute = int(hh), int(mm)
        except (ValueError, AttributeError):
            raise ValueError("실행 시각은 HH:MM 형식이어야 합니다 (예: 09:30)") from None
        if not (9 <= hour <= 15) or not (0 <= minute <= 59):
            raise ValueError("실행 시각은 09:00~15:00 KST 범위여야 합니다")
        return f"{hour:02d}:{minute:02d}"


class RebalancingAlertResponse(BaseModel):
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
    auto_execution_time: str | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _build_response(alert: RebalancingAlert) -> RebalancingAlertResponse:
    return RebalancingAlertResponse(
        id=alert.id,
        portfolio_id=alert.portfolio_id,
        is_active=alert.is_active,
        threshold_pct=float(alert.threshold_pct),
        schedule_type=alert.schedule_type,
        schedule_day_of_week=alert.schedule_day_of_week,
        schedule_day_of_month=alert.schedule_day_of_month,
        trigger_condition=alert.trigger_condition,
        mode=alert.mode,
        strategy=alert.strategy,
        account_id=alert.account_id,
        order_type=alert.order_type,
        market_condition_mode=alert.market_condition_mode,
        auto_execution_time=getattr(alert, "auto_execution_time", None),
        last_triggered_at=alert.last_triggered_at,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("/rebalancing", response_model=list[RebalancingAlertResponse])
@limiter.limit("30/minute")
async def list_rebalancing_alerts(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """내 리밸런싱 알림 목록 조회."""
    result = await db.execute(
        select(RebalancingAlert)
        .where(RebalancingAlert.user_id == current_user.id)
        .order_by(RebalancingAlert.created_at)
    )
    alerts = result.scalars().all()
    return [_build_response(a) for a in alerts]


@router.get("/rebalancing/{portfolio_id}", response_model=RebalancingAlertResponse)
@limiter.limit("30/minute")
async def get_rebalancing_alert(
    request: Request,
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
    return _build_response(alert)


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

    if body.mode == "AUTO" and body.account_id is not None:
        exec_account = await db.scalar(
            select(AssetAccount).where(
                AssetAccount.id == body.account_id,
                AssetAccount.user_id == current_user.id,
            )
        )
        if not exec_account or exec_account.asset_type != "STOCK_KIS":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="자동 실행 계좌는 KIS 연동 계좌만 사용할 수 있습니다",
            )

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
        alert.auto_execution_time = body.auto_execution_time
        alert.is_active = True
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
            auto_execution_time=body.auto_execution_time,
            is_active=True,
        )
        db.add(alert)

    await db.commit()
    await db.refresh(alert)
    return _build_response(alert)


@router.delete("/rebalancing/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def delete_rebalancing_alert(
    request: Request,
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
