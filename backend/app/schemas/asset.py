from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

AssetType = Literal[
    "BANK_ACCOUNT", "DEPOSIT", "STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER",
    "CASH_OTHER", "OTHER", "REAL_ESTATE",
]
DataSource = Literal["MANUAL", "KIS_API", "KIWOOM_API", "OPEN_BANKING"]
TransactionType = Literal["DEPOSIT", "WITHDRAWAL", "DIVIDEND"]


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


def _validate_positive(v: float | None) -> float | None:
    if v is not None and v <= 0:
        raise ValueError("금액은 0보다 커야 합니다")
    return v


class AssetAccountCreate(BaseModel):
    name: str
    asset_type: AssetType
    data_source: DataSource = "MANUAL"
    institution: str | None = None
    kis_account_no: str | None = None
    kis_app_key: str | None = None     # 계좌별 KIS App Key (평문, 저장 시 암호화)
    kis_app_secret: str | None = None  # 계좌별 KIS App Secret (평문, 저장 시 암호화)
    kiwoom_account_no: str | None = None
    kiwoom_app_key: str | None = None     # 키움 App Key (평문, 저장 시 암호화)
    kiwoom_app_secret: str | None = None  # 키움 App Secret (평문, 저장 시 암호화)
    ob_fintech_use_no: str | None = None
    ob_bank_code: str | None = None
    is_mock_mode: bool = True
    manual_amount: float | None = None
    manual_currency: str = "KRW"
    deposit_krw: float | None = None
    notes: str | None = None
    sort_order: int = 0
    real_estate_details: RealEstateDetails | None = None
    include_in_total: bool = True

    @field_validator("manual_amount")
    @classmethod
    def manual_amount_positive(cls, v: float | None) -> float | None:
        return _validate_positive(v)


class AssetAccountUpdate(BaseModel):
    name: str | None = None
    institution: str | None = None
    kis_app_key: str | None = None     # 계좌별 KIS App Key (평문, 저장 시 암호화)
    kis_app_secret: str | None = None  # 계좌별 KIS App Secret (평문, 저장 시 암호화)
    kiwoom_app_key: str | None = None     # 키움 App Key (평문, 저장 시 암호화)
    kiwoom_app_secret: str | None = None  # 키움 App Secret (평문, 저장 시 암호화)
    manual_amount: float | None = None
    deposit_krw: float | None = None
    notes: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    real_estate_details: RealEstateDetails | None = None
    include_in_total: bool | None = None

    @field_validator("manual_amount")
    @classmethod
    def manual_amount_positive(cls, v: float | None) -> float | None:
        return _validate_positive(v)


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
    real_estate_details: dict | None = None
    include_in_total: bool
    is_active: bool
    sort_order: int
    notes: str | None
    created_at: datetime
    has_own_kis_credentials: bool = False     # KIS 계좌별 API 키 보유 여부
    has_own_kiwoom_credentials: bool = False  # 키움 계좌별 API 키 보유 여부

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

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        return _validate_positive(v)  # type: ignore[return-value]


class TransactionUpdate(BaseModel):
    transaction_type: TransactionType | None = None
    amount: float | None = None
    transaction_date: date | None = None
    ticker: str | None = None
    notes: str | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float | None) -> float | None:
        return _validate_positive(v)


class TransactionResponse(BaseModel):
    id: UUID
    account_id: UUID | None
    transaction_type: TransactionType
    amount: float
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
    goal_annual_return_pct: float | None = None
    retirement_target_year: int | None = None
