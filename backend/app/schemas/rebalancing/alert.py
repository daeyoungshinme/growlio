"""리밸런싱 알림 설정 스키마."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


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
    # NOTIFY 모드 알림 발송 시각 (HH:MM KST, 기본: "08:30")
    notify_time: str = "08:30"
    # AUTO 모드 매수 대기시간(분) — 플랜 이메일 발송 후 이 시간 뒤 자동 실행(취소 가능)
    buy_wait_minutes: int = 10
    # 세금영향 게이트: DISABLED(기본) | ENABLED — 매도로 인한 추정 양도세가 max_tax_impact_krw를 넘으면 AUTO 보류
    tax_impact_gate_mode: Literal["DISABLED", "ENABLED"] = "DISABLED"
    max_tax_impact_krw: float | None = None

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

    @field_validator("notify_time")
    @classmethod
    def validate_notify_time(cls, v: str) -> str:
        try:
            hh, mm = v.split(":")
            hour, minute = int(hh), int(mm)
        except (ValueError, AttributeError):
            raise ValueError("알림 시각은 HH:MM 형식이어야 합니다 (예: 08:30)") from None
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ValueError("알림 시각은 00:00~23:59 범위여야 합니다")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("buy_wait_minutes")
    @classmethod
    def validate_buy_wait_minutes(cls, v: int) -> int:
        if not (1 <= v <= 120):
            raise ValueError("매수 대기시간은 1~120분 사이여야 합니다")
        return v

    @field_validator("max_tax_impact_krw")
    @classmethod
    def validate_max_tax_impact_krw(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("세금영향 상한은 0보다 커야 합니다")
        return v


class AlertScopeUpdate(BaseModel):
    alert_scope: Literal["AGGREGATE", "PER_ACCOUNT"]


class TestAlertResponse(BaseModel):
    email_sent: bool
    push_sent: bool
    message: str


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
    notify_time: str
    buy_wait_minutes: int
    tax_impact_gate_mode: str
    max_tax_impact_krw: float | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime
