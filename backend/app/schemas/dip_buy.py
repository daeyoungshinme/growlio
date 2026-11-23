"""낙폭 추매 안내(plans/147) 요청·응답 스키마."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas._validators import NonNegativeAmount, PositiveAmount
from app.services.dip_buy_calculator import validate_tiers


class DipBuyTier(BaseModel):
    drawdown_pct: float = Field(..., ge=1, le=60)
    ratio_pct: float = Field(..., ge=1, le=100)


class DipBuyPlanUpsert(BaseModel):
    index_ticker: Literal["QQQ", "SPY"] = "QQQ"
    reserve_krw: NonNegativeAmount
    tiers: list[DipBuyTier]
    is_active: bool = True

    @field_validator("tiers")
    @classmethod
    def _tiers(cls, v: list[DipBuyTier]) -> list[DipBuyTier]:
        error = validate_tiers([t.model_dump() for t in v])
        if error:
            raise ValueError(error)
        return v


class DipBuyComplete(BaseModel):
    """추매 완료 기록 — `amount_krw`는 실제로 산 금액(없으면 안내 금액)."""

    amount_krw: PositiveAmount | None = None


class DipBuyTierStatus(BaseModel):
    tier: int
    drawdown_pct: float
    ratio_pct: float
    amount_krw: float
    state: Literal["DONE", "DUE", "WAITING"]
    done_amount_krw: float | None = None


class DipBuyItem(BaseModel):
    ticker: str
    name: str
    market: str
    shares: float
    amount_krw: float
    price_krw: float
    amount_usd: float | None = None  # 해외 종목이면 필요 달러(환율 실값일 때만)


class DipBuyPlanStatus(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    portfolio_name: str
    is_active: bool
    index_ticker: str
    reserve_krw: float
    cycle_base_krw: float | None
    tiers: list[DipBuyTierStatus]
    drawdown_pct: float | None  # 52주 고점 대비(%, 0 이하). None = 확인 불가
    # 정기 적립식 자동매수(실행 계좌·적립일 기준)가 없으면 False — 종목 분할·적립일 안내를 할 수 없다
    has_dca_schedule: bool
    next_run_date: date | None
    is_run_day: bool
    due_amount_krw: float
    due_tiers: list[int]
    items: list[DipBuyItem]
    leftover_krw: float  # 1주 단위로 나누고 남은 금액


class DipBuyStatusResponse(BaseModel):
    plans: list[DipBuyPlanStatus]
    reset_drawdown_pct: float
