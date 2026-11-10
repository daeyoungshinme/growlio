"""알림 API 스키마 — 환율·주가 목표 알림 CRUD와 알림 이력 조회."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from app.kis.constants import OVERSEAS_MARKETS
from app.schemas._validators import MAX_AMOUNT_KRW

# 해외 주가 알림 목표가가 이 원화 값보다 작으면 달러 숫자를 원화로 저장한 것으로 본다($1 ≈ 1,300원 이상).
# plans/118 C6 이전 화면은 해외 종목도 "목표가 (원)"으로 받아 SCHD $27이 27원으로 저장됐다(plans/119 A3).
SUSPECT_USD_UNIT_MAX_KRW = 1_000.0


def is_suspect_usd_unit(market: str, target_price: float) -> bool:
    """해외 종목 목표가가 달러 숫자 그대로 원화 칸에 저장된 것으로 보이는지."""
    return market in OVERSEAS_MARKETS and float(target_price) < SUSPECT_USD_UNIT_MAX_KRW


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
    source: Literal["MANUAL", "FX_PLAN"] = "MANUAL"
    planned_usd: float | None = None
    portfolio_id: uuid.UUID | None = None


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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def needs_reentry(self) -> bool:
        """목표가 단위가 의심돼 판정에서 빠진 알림 — 화면이 다시 입력하라고 안내한다."""
        return is_suspect_usd_unit(self.market, self.target_price)


class AlertHistoryItem(BaseModel):
    id: uuid.UUID
    alert_type: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}
