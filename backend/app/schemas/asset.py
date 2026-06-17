import re
from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.enums import AssetType, DataSource, TransactionType
from app.models.asset import VALID_MARKETS


class ManualPosition(BaseModel):
    """수동 종목 입력 스키마."""

    ticker: str
    name: str
    market: str = "KOSPI"
    qty: float
    avg_price: float
    avg_price_usd: float | None = None
    usd_rate: float | None = None
    current_price: float | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("종목명은 빈 값일 수 없습니다")
        if len(stripped) > 200:
            raise ValueError("종목명은 200자 이하여야 합니다")
        return stripped

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("티커는 빈 값일 수 없습니다")
        if len(stripped) > 20:
            raise ValueError("티커는 20자 이하여야 합니다")
        return stripped.upper()

    @field_validator("qty")
    @classmethod
    def qty_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("수량은 0보다 커야 합니다")
        if v > 1_000_000:
            raise ValueError("수량은 1,000,000 이하여야 합니다")
        return v

    @field_validator("avg_price")
    @classmethod
    def avg_price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("평균단가는 0보다 커야 합니다")
        return v

    @field_validator("avg_price_usd")
    @classmethod
    def avg_price_usd_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("달러 평균단가는 0보다 커야 합니다")
        return v

    @field_validator("usd_rate")
    @classmethod
    def usd_rate_range(cls, v: float | None) -> float | None:
        if v is not None and not (0 < v < 10000):
            raise ValueError("환율은 0 초과 10,000 미만이어야 합니다")
        return v

    @field_validator("market")
    @classmethod
    def market_valid(cls, v: str) -> str:
        if v not in VALID_MARKETS:
            raise ValueError(f"유효하지 않은 시장: {v}. 허용값: {sorted(VALID_MARKETS)}")
        return v


class PositionItem(BaseModel):
    ticker: str
    market: str
    qty: float
    avg_price: float
    name: str | None = None


class RealEstateDetails(BaseModel):
    address: str
    property_type: str
    purchase_price_krw: float | None = None
    purchase_date: str | None = None
    mortgage_balance_krw: float = 0.0

    @model_validator(mode="after")
    def mortgage_not_exceed_value(self) -> "RealEstateDetails":
        if self.purchase_price_krw is not None and self.mortgage_balance_krw > self.purchase_price_krw:
            raise ValueError("모기지 잔액이 부동산 가치를 초과할 수 없습니다")
        return self


def _validate_positive(v: float | None) -> float | None:
    if v is not None and v <= 0:
        raise ValueError("금액은 0보다 커야 합니다")
    return v


def _validate_non_negative(v: float | None) -> float | None:
    if v is not None and v < 0:
        raise ValueError("금액은 0 이상이어야 합니다")
    return v


class AssetAccountCreate(BaseModel):
    name: str
    asset_type: AssetType
    data_source: DataSource = DataSource.MANUAL
    institution: str | None = None
    kis_account_no: str | None = None
    kis_app_key: str | None = None  # 계좌별 KIS App Key (평문, 저장 시 암호화)
    kis_app_secret: str | None = None  # 계좌별 KIS App Secret (평문, 저장 시 암호화)
    kiwoom_account_no: str | None = None
    kiwoom_app_key: str | None = None  # 키움 App Key (평문, 저장 시 암호화)
    kiwoom_app_secret: str | None = None  # 키움 App Secret (평문, 저장 시 암호화)
    ob_fintech_use_no: str | None = None
    ob_bank_code: str | None = None
    is_mock_mode: bool = True
    manual_amount: float | None = None
    manual_currency: str = "KRW"
    deposit_krw: float | None = None
    deposit_usd: float | None = None
    notes: str | None = None
    sort_order: int = 0
    real_estate_details: RealEstateDetails | None = None
    include_in_total: bool = True

    @field_validator("deposit_krw", "deposit_usd")
    @classmethod
    def deposit_non_negative(cls, v: float | None) -> float | None:
        return _validate_non_negative(v)

    @field_validator("kis_account_no")
    @classmethod
    def kis_account_no_format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.fullmatch(r"\d{8}-\d{2}|\d{10}", v):
            raise ValueError("KIS 계좌번호 형식이 올바르지 않습니다. 예: 12345678-01")
        return v

    @field_validator("manual_amount")
    @classmethod
    def manual_amount_positive(cls, v: float | None) -> float | None:
        return _validate_positive(v)

    @model_validator(mode="after")
    def kis_credentials_required(self) -> "AssetAccountCreate":
        if self.data_source == "KIS_API":
            if not self.kis_account_no:
                raise ValueError("KIS 계좌번호를 입력하세요.")
            if not self.kis_app_key or not self.kis_app_secret:
                raise ValueError("KIS App Key와 App Secret을 입력하세요.")
        return self


class AssetAccountUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    kis_app_key: str | None = None  # 계좌별 KIS App Key (평문, 저장 시 암호화)
    kis_app_secret: str | None = None  # 계좌별 KIS App Secret (평문, 저장 시 암호화)
    kiwoom_app_key: str | None = None  # 키움 App Key (평문, 저장 시 암호화)
    kiwoom_app_secret: str | None = None  # 키움 App Secret (평문, 저장 시 암호화)
    manual_amount: float | None = None
    deposit_krw: float | None = None
    deposit_usd: float | None = None
    notes: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    real_estate_details: RealEstateDetails | None = None
    include_in_total: bool | None = None

    @field_validator("manual_amount")
    @classmethod
    def manual_amount_positive(cls, v: float | None) -> float | None:
        return _validate_positive(v)

    @field_validator("deposit_krw", "deposit_usd")
    @classmethod
    def deposit_non_negative(cls, v: float | None) -> float | None:
        return _validate_non_negative(v)


class AssetAccountResponse(BaseModel):
    id: UUID
    name: str
    asset_type: AssetType
    data_source: DataSource
    institution: str | None
    kis_account_no: str | None = None
    kiwoom_account_no: str | None = None
    is_mock_mode: bool
    manual_amount: float | None
    manual_currency: str
    manual_updated_at: datetime | None
    manual_positions: list[Any] | None = None
    deposit_krw: float | None = None
    deposit_usd: float | None = None
    real_estate_details: dict | None = None
    include_in_total: bool
    is_active: bool
    sort_order: int
    notes: str | None
    created_at: datetime
    has_own_kis_credentials: bool = False  # KIS 계좌별 API 키 보유 여부
    has_own_kiwoom_credentials: bool = False  # 키움 계좌별 API 키 보유 여부
    target_portfolio_id: UUID | None = None

    model_config = {"from_attributes": True}


class AssetSnapshotResponse(BaseModel):
    id: UUID
    account_id: UUID | None
    snapshot_date: date
    amount_krw: float
    currency: str
    invested_amount: float | None
    unrealized_pnl: float | None
    positions: list[Any] | None
    source: str

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    account_id: UUID | None = None
    transaction_type: TransactionType
    amount: float
    transaction_date: date
    ticker: str | None = None
    notes: str | None = None
    fee: float | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        return _validate_positive(v)  # type: ignore[return-value]

    @field_validator("fee")
    @classmethod
    def fee_non_negative(cls, v: float | None) -> float | None:
        return _validate_non_negative(v)


class TransactionUpdate(BaseModel):
    transaction_type: TransactionType | None = None
    amount: float | None = None
    transaction_date: date | None = None
    ticker: str | None = None
    notes: str | None = None
    fee: float | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float | None) -> float | None:
        return _validate_positive(v)

    @field_validator("fee")
    @classmethod
    def fee_non_negative(cls, v: float | None) -> float | None:
        return _validate_non_negative(v)


class TransactionResponse(BaseModel):
    id: UUID
    account_id: UUID | None
    transaction_type: TransactionType
    amount: float
    fee: float | None
    transaction_date: date
    ticker: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DashboardResponse(BaseModel):
    total_assets_krw: float
    asset_allocation: list[dict]
    goal_amount: float | None
    goal_achievement_pct: float | None
    stock_return_pct: float
    annual_return_pct: float | None
    monthly_trend: list[dict]
    annual_deposit_goal: float | None = None
    deposit_achievement_pct: float | None = None
    annual_dividends_received: float | None = None
    estimated_annual_dividends: float | None = None
    dividend_monthly_breakdown: list[dict] = []
    cumulative_return_pct: float | None = None
    xirr_pct: float | None = Field(None, ge=-99, le=1000)
    xirr_is_estimated: bool = False
    goal_annual_return_pct: float | None = None
    retirement_target_year: int | None = None
