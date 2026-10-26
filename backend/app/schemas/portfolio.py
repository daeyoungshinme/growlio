"""통합 포트폴리오 Pydantic 스키마 (백테스팅·리밸런싱 공용)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.enums import AccountTaxType, InvestmentHorizon, PortfolioBaseType
from app.schemas._validators import validate_portfolio_weights, validate_portfolio_weights_optional


class PortfolioGroupMember(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    market: str = Field(max_length=20)
    name: str = Field(default="", max_length=200)
    # 정방향 레버리지 배수 — 그룹 비중은 노출 기준(평가액 × 배수)으로 합산한다(QLD=2). 국내 대체 매수 종목은 1만 허용
    leverage: float = Field(default=1.0, ge=1, le=3)


class PortfolioItemGroup(BaseModel):
    """지수 그룹 항목(plans/74) — 항목의 ticker/market이 대표 매수 종목, members는 그 외 합산 종목."""

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=50)
    members: list[PortfolioGroupMember] = Field(default=[], max_length=30)
    # ISA·연금저축·IRP 계좌에서 대표 종목(해외 상장) 대신 매수할 국내 상장 종목 — 그룹 합산에도 포함
    domestic_alt: PortfolioGroupMember | None = None


class PortfolioItem(BaseModel):
    model_config = {"from_attributes": True}

    # 길이 상한 = DB 컬럼 길이 — 넘으면 422 대신 DB 오류 500이 났다(계획 57 C5).
    # 응답에도 쓰이지만 저장값은 이미 컬럼 길이 안이라 영향이 없다
    ticker: str = Field(max_length=20)
    name: str = Field(default="", max_length=200)  # 자동완성 없이 추가 시 빈 문자열 허용
    market: str = Field(max_length=20)
    weight: float  # 0~100, 합계 = 100
    group: PortfolioItemGroup | None = None


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    items: list[PortfolioItem] = Field(max_length=100)
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
    name: str | None = Field(default=None, min_length=1, max_length=100)
    items: list[PortfolioItem] | None = Field(default=None, max_length=100)
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
    sort_order: int = Field(ge=0, le=10_000)


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


class IndexExposureMember(BaseModel):
    ticker: str
    name: str
    market: str
    listing: Literal["DOMESTIC", "OVERSEAS"]
    value_krw: float
    hedged: bool = False
    pct_of_stock: float
    region: Literal["DOMESTIC", "OVERSEAS"] | None = None  # 실제 투자지역(판별 불가면 None)
    # 정방향 레버리지(LEVERAGED 그룹)의 기초 지수·배수 — 리밸런싱 지수 그룹 제안이 원 지수 그룹에 합친다
    underlying_index_key: str | None = None
    leverage: float = 1.0


class IndexExposureGroup(BaseModel):
    key: str
    label: str
    kind: Literal["INDEX", "LEVERAGED", "OTHER_ETF", "STOCK"]
    value_krw: float
    pct_of_stock: float
    pct_of_etf: float | None  # STOCK 그룹은 None
    has_hedged: bool = False
    domestic_krw: float
    overseas_krw: float
    members: list[IndexExposureMember]


class RegionExposure(BaseModel):
    """실제 투자지역 기준 국내/해외 합계 — 국내상장 미국 ETF는 해외로 계산. 세 값의 합 = total_stock_krw."""

    domestic_krw: float = 0.0
    overseas_krw: float = 0.0
    unknown_krw: float = 0.0


class IndexExposureResponse(BaseModel):
    """추종 지수별 비중(`GET /portfolio/index-exposure`)."""

    total_stock_krw: float = 0.0
    total_etf_krw: float = 0.0
    groups: list[IndexExposureGroup] = []
    region_exposure: RegionExposure = RegionExposure()
    profiles_complete: bool = True  # False면 일부 종목의 ETF 정보 조회 실패 — 분류가 부정확할 수 있음


class IndexGroupSuggestionMember(PortfolioGroupMember):
    value_krw: float = 0.0  # 현재 보유 평가액(전체 계좌, 미보유 후보는 0)
    # 분석 대상 계좌에 보유 중인지 — False면 다른 계좌에만 있어 그 계좌를 분석 대상에 추가해야 합산된다
    in_scope: bool = True
    account_names: list[str] = []  # 보유 계좌 이름


class IndexGroupSuggestion(BaseModel):
    """지수 그룹 제안(`GET /portfolios/index-group-suggestions`, plans/74) — 저장 안 함, 편집기가 골라 쓴다."""

    key: str
    label: str
    value_krw: float  # 멤버 평가액 합계
    exposure_krw: float  # 노출 합계(평가액 × 레버리지 배수) — 리밸런싱이 이탈을 판단하는 기준
    pct_of_stock: float
    primary: IndexGroupSuggestionMember  # 기본 대표 매수 종목
    domestic_alt: IndexGroupSuggestionMember | None = None  # 기본 국내 대체 매수 종목(대표가 해외 상장일 때만)
    members: list[IndexGroupSuggestionMember]  # 이 지수를 추종하는 보유 종목(대표 포함)
    primary_candidates: list[IndexGroupSuggestionMember]  # 대표로 고를 수 있는 종목(보유 → 큐레이션 순)
    domestic_alt_candidates: list[IndexGroupSuggestionMember]


class IndexGroupSuggestionResponse(BaseModel):
    groups: list[IndexGroupSuggestion] = []
    profiles_complete: bool = True
