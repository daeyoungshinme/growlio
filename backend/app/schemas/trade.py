"""수기 매매 기록 + 기간별 매수 현황 스키마 (trades.py 전용)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.enums import TradeSide
from app.schemas._validators import validate_non_negative_amount, validate_positive_amount


class TradeCreate(BaseModel):
    account_id: UUID
    side: TradeSide
    ticker: str = Field(min_length=1, max_length=20)
    market: str = Field(min_length=1, max_length=20)
    name: str = Field(default="", max_length=200)
    qty: float = Field(gt=0, le=1_000_000_000)
    price_krw: float
    fee: float | None = None
    trade_date: date
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("price_krw")
    @classmethod
    def price_positive(cls, v: float) -> float:
        return validate_positive_amount(v)  # type: ignore[return-value]

    @field_validator("fee")
    @classmethod
    def fee_non_negative(cls, v: float | None) -> float | None:
        return validate_non_negative_amount(v)


class TradeUpdate(BaseModel):
    side: TradeSide | None = None
    qty: float | None = Field(default=None, gt=0, le=1_000_000_000)
    price_krw: float | None = None
    fee: float | None = None
    trade_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("price_krw")
    @classmethod
    def price_positive(cls, v: float | None) -> float | None:
        return validate_positive_amount(v)

    @field_validator("fee")
    @classmethod
    def fee_non_negative(cls, v: float | None) -> float | None:
        return validate_non_negative_amount(v)


class TradeResponse(BaseModel):
    id: UUID
    account_id: UUID | None
    side: TradeSide
    ticker: str
    market: str
    name: str
    qty: float
    price_krw: float
    fee: float | None
    trade_date: date
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PeriodPurchaseItem(BaseModel):
    account_id: UUID
    account_name: str
    ticker: str
    market: str
    name: str
    source: str  # ESTIMATED | MANUAL
    bought_qty: float
    bought_amount_krw: float
    avg_buy_price_krw: float
    held_qty: float
    held_cost_krw: float
    current_price_krw: float | None
    value_krw: float
    unrealized_pnl_krw: float
    realized_pnl_krw: float
    total_pnl_krw: float
    cost_basis_krw: float
    return_pct: float | None
    first_buy_date: date | None
    partially_sold: bool
    price_estimated: bool


class PeriodPurchaseTotals(BaseModel):
    bought_amount_krw: float
    held_cost_krw: float
    value_krw: float
    realized_pnl_krw: float
    total_pnl_krw: float
    return_pct: float | None


class TrackingStartedAccount(BaseModel):
    account_id: UUID
    account_name: str
    since: date


class PeriodPurchaseSummary(BaseModel):
    start: date
    end: date
    items: list[PeriodPurchaseItem]
    summary: PeriodPurchaseTotals
    tracking_started: list[TrackingStartedAccount]
