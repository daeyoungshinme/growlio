"""통합 포트폴리오 Pydantic 스키마 (백테스팅·리밸런싱 공용)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.enums import PortfolioBaseType
from app.schemas._validators import validate_portfolio_weights, validate_portfolio_weights_optional

# ---------------------------------------------------------------------------
# KIS 실시간 포트폴리오 서머리 (/portfolio/summary) 응답 스키마
# ---------------------------------------------------------------------------


class DomesticPosition(BaseModel):
    ticker: str
    name: str
    market: str
    qty: int
    avg_price: float
    current_price: float
    value_krw: float
    pnl: float
    pnl_pct: float
    currency: str = "KRW"


class OverseasPosition(BaseModel):
    ticker: str
    name: str
    market: str
    qty: int
    avg_price: float
    current_price: float
    value_usd: float
    pnl_usd: float
    pnl_pct: float
    currency: str = "USD"


class DomesticBalance(BaseModel):
    total_value_krw: float
    invested_krw: float
    pnl_krw: float
    deposit_krw: float
    positions: list[DomesticPosition]


class OverseasBalance(BaseModel):
    total_value_usd: float
    deposit_usd: float
    positions: list[OverseasPosition]


class KisAccountDetail(BaseModel):
    account_no: str
    domestic: DomesticBalance
    overseas: OverseasBalance


class PortfolioSummaryResponse(BaseModel):
    domestic: DomesticBalance
    overseas: OverseasBalance
    total_value_krw: float
    total_invested_krw: float
    unrealized_pnl_krw: float
    stock_return_pct: float
    is_mock: bool
    accounts: list[KisAccountDetail]


class PortfolioItem(BaseModel):
    model_config = {"from_attributes": True}

    ticker: str
    name: str = ""  # 자동완성 없이 추가 시 빈 문자열 허용
    market: str
    weight: float  # 0~100, 합계 = 100


class PortfolioCreate(BaseModel):
    name: str
    items: list[PortfolioItem]
    base_type: PortfolioBaseType = PortfolioBaseType.STOCK_ONLY
    account_ids: list[uuid.UUID] | None = None  # null이면 모든 활성 주식 계좌 사용

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[PortfolioItem]) -> list[PortfolioItem]:
        return validate_portfolio_weights(v)


class PortfolioUpdate(BaseModel):
    name: str | None = None
    items: list[PortfolioItem] | None = None
    base_type: PortfolioBaseType | None = None
    account_ids: list[uuid.UUID] | None = None  # [] 전송 시 null로 초기화 (전체 계좌 사용)

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[PortfolioItem] | None) -> list[PortfolioItem] | None:
        return validate_portfolio_weights_optional(v)


class PortfolioReorderItem(BaseModel):
    id: uuid.UUID
    sort_order: int


class PortfolioReorderRequest(BaseModel):
    items: list[PortfolioReorderItem]

    @model_validator(mode="after")
    def validate_not_empty(self) -> "PortfolioReorderRequest":
        if not self.items:
            raise ValueError("items는 최소 1개 이상이어야 합니다.")
        return self


class PortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    items: list[PortfolioItem]
    base_type: str
    account_ids: list[str] | None = None  # Portfolio.account_ids property에서 자동 변환
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
