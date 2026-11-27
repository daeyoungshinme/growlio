"""낙폭 추매 안내(plans/147·148) 요청·응답 스키마."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas._validators import NonNegativeAmount, PositiveAmount
from app.services.dip_buy_calculator import NOTIFY_DAY_RANGE, validate_tiers

DipBuyIndex = Literal["QQQ", "SPY"]
NotifyMode = Literal["ON_REACH", "MONTHLY_DAY"]


class DipBuyTier(BaseModel):
    drawdown_pct: float = Field(..., ge=1, le=60)
    ratio_pct: float = Field(..., ge=1, le=100)


class DipBuySettingsUpsert(BaseModel):
    reserve_krw: NonNegativeAmount
    notify_mode: NotifyMode = "ON_REACH"
    notify_day: int | None = Field(None, ge=NOTIFY_DAY_RANGE[0], le=NOTIFY_DAY_RANGE[1])
    is_active: bool = True

    @model_validator(mode="after")
    def _day_required(self) -> DipBuySettingsUpsert:
        if self.notify_mode == "MONTHLY_DAY" and self.notify_day is None:
            raise ValueError("매달 알림 받을 날짜를 정해주세요.")
        return self


class DipBuyRuleUpsert(BaseModel):
    index_ticker: DipBuyIndex
    allocation_pct: float = Field(..., ge=1, le=100)
    tiers: list[DipBuyTier]
    is_active: bool = True
    # 배분 합계가 100을 넘으면 다른 규칙 배분을 비율대로 줄여 맞춘다(끄면 400)
    shrink_others: bool = False

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


class DipBuyEtf(BaseModel):
    """안내 금액으로 이 ETF만 산다면 — 같은 지수 ETF끼리는 대안."""

    ticker: str
    name: str
    market: str
    price_krw: float
    shares: int
    amount_krw: float
    amount_usd: float | None = None  # 해외 종목이면 필요 달러(환율 실값일 때만)
    price_usd: float | None = None  # 해외 종목 1주 달러가(환율 실값일 때만)
    tier_price_krw: list[float] = []  # 규칙 구간 순서대로 도달 시 1주가 추정(낙폭 모르면 빈 목록)
    tier_price_usd: list[float] | None = None  # 해외 종목·환율 실값일 때만


class DipBuySettingsOut(BaseModel):
    reserve_krw: float
    notify_mode: NotifyMode
    notify_day: int | None
    is_active: bool


class DipBuyRuleStatus(BaseModel):
    id: uuid.UUID
    index_ticker: DipBuyIndex
    allocation_pct: float
    is_active: bool
    base_krw: float  # 이 규칙 몫(사이클 중이면 고정 기준액)
    spent_krw: float  # 이번 사이클 추매액
    remaining_krw: float
    tiers: list[DipBuyTierStatus]
    drawdown_pct: float | None  # 52주 고점 대비(%, 0 이하). None = 확인 불가
    due_amount_krw: float
    due_tiers: list[int]
    etfs: list[DipBuyEtf]
    reset_drawdown_pct: float  # 고점 대비 이 % 이내로 회복하면 사이클 종료(3%와 첫 구간 절반 중 얕은 값)


class DipBuyStatusResponse(BaseModel):
    settings: DipBuySettingsOut | None
    rules: list[DipBuyRuleStatus]
    next_notify_date: date | None  # 알림 방식이 매달 정한 날일 때만
    due_amount_krw: float
    # 전술 연동 정기 적립식 자동매수가 방어 국면이라 보류 중인 포트폴리오(추매는 별개로 안내)
    dca_held_portfolios: list[str]
    # 등록 후보 ETF 중 QQQ·SPY 지수를 추종하는 ETF가 하나라도 있는지(없으면 금액만 안내)
    has_candidates: bool
    # 지수별 52주 고점 대비 낙폭(규칙이 없는 지수도) — None = 확인 불가
    index_drawdowns: dict[str, float | None]
    reset_drawdown_pct: float
