"""통합 포트폴리오 Pydantic 스키마 (백테스팅·리밸런싱 공용)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.enums import AccountTaxType, InvestmentHorizon, PortfolioBaseType
from app.schemas._validators import validate_portfolio_weights, validate_portfolio_weights_optional


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
    # 명시적 기간/세제유형 태그 — 미지정이면 기준 포트폴리오 지정 계좌들의 태그로부터 추론
    investment_horizon: InvestmentHorizon | None = None
    tax_type: AccountTaxType | None = None

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[PortfolioItem]) -> list[PortfolioItem]:
        return validate_portfolio_weights(v)


class PortfolioUpdate(BaseModel):
    name: str | None = None
    items: list[PortfolioItem] | None = None
    base_type: PortfolioBaseType | None = None
    account_ids: list[uuid.UUID] | None = None  # [] 전송 시 null로 초기화 (전체 계좌 사용)
    # None/미전송 구분은 model_fields_set으로 판별 — 명시적으로 null을 보내면 태그 해제(추론으로 복귀)
    investment_horizon: InvestmentHorizon | None = None
    tax_type: AccountTaxType | None = None

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
    alert_scope: str = "AGGREGATE"  # AGGREGATE | PER_ACCOUNT
    investment_horizon: InvestmentHorizon | None = None
    tax_type: AccountTaxType | None = None
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime
