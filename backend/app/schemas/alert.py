"""알림 API 스키마 — 환율·주가 목표 알림 CRUD와 알림 이력 조회."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas._validators import MAX_AMOUNT_KRW


class ExchangeRateAlertCreate(BaseModel):
    # target_rate 컬럼은 Numeric(10,2) — 상한이 없으면 큰 값이 DB 오버플로 500이 됐다(계획 57 C5)
    target_rate: float = Field(le=100_000, allow_inf_nan=False)
    direction: Literal["BELOW", "ABOVE"]
    max_trigger_count: int = Field(default=1, le=1000)

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


class ExchangeRateAlertResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    target_rate: float
    direction: str
    is_active: bool
    max_trigger_count: int
    trigger_count: int
    triggered_at: datetime | None
    created_at: datetime


class StockPriceAlertCreate(BaseModel):
    # 길이·범위 상한 = DB 컬럼(String(20)/String(100)/Numeric(18,2)) — 넘으면 422 대신 500이 났다(계획 57 C5)
    ticker: str = Field(min_length=1, max_length=20)
    market: str = Field(min_length=1, max_length=20)
    name: str = Field(max_length=100)
    target_price: float = Field(le=MAX_AMOUNT_KRW, allow_inf_nan=False)
    direction: Literal["BELOW", "ABOVE"]
    max_trigger_count: int = Field(default=1, le=1000)

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


class AlertHistoryItem(BaseModel):
    id: uuid.UUID
    alert_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}
