"""외부 서비스(nestlio) API(`api/v1/external.py`) 요청·응답 스키마."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.enums import AssetType, TransactionType
from app.schemas._validators import PositiveAmount


class ExternalAccountBalance(BaseModel):
    id: str
    name: str
    asset_type: AssetType
    current_value_krw: float
    as_of: date | None = None
    # 최신 스냅샷의 투자 원금/평가손익 — 스냅샷이 없거나 원금을 추적하지 않는 계좌(예금 등)는 None.
    invested_amount_krw: float | None = None
    unrealized_pnl_krw: float | None = None


class ExternalPerformance(BaseModel):
    xirr_pct: float | None = None
    annual_return_pct: float | None = None
    cumulative_return_pct: float | None = None
    goal_annual_return_pct: float | None = None
    return_goal_gap_pct: float | None = None
    annual_deposit_goal: float | None = None
    annual_deposit_current: float | None = None
    deposit_achievement_pct: float | None = None


class ExternalRealEstateItem(BaseModel):
    id: str
    name: str
    address: str | None = None
    property_type: str | None = None
    market_value_krw: float
    mortgage_balance_krw: float
    net_equity_krw: float
    purchase_price_krw: float | None = None
    purchase_date: str | None = None
    as_of: date | None = None


class ExternalGoalSettings(BaseModel):
    is_configured: bool
    goal_amount: float | None = None
    goal_annual_return_pct: float | None = None
    goal_start_date: datetime | None = None
    goal_initial_amount: float | None = None
    annual_deposit_goal: float | None = None
    annual_dividend_goal: float | None = None


class ExternalTransactionCreate(BaseModel):
    account_id: UUID
    transaction_type: TransactionType
    # 내부 TransactionCreate와 같은 규칙 — 음수 DEPOSIT이 MANUAL 계좌 예수금을 깎거나 Numeric 오버플로로 500이 나지 않게
    amount: PositiveAmount
    transaction_date: date
    notes: str | None = Field(default=None, max_length=1000)
    # 멱등 키 — 같은 사용자가 같은 키로 다시 보내면 새로 기록하지 않는다(nestlio: "nestlio:{거래id}:{동작}").
    external_ref: str | None = Field(default=None, min_length=1, max_length=100)


class ExternalTransactionResult(BaseModel):
    transaction_id: str
    deposit_krw_adjusted: bool
    deposit_krw: float | None = None
    # True면 같은 external_ref로 이미 기록돼 있어 아무것도 바꾸지 않았다.
    duplicate: bool = False


class ExternalNetDeposit(BaseModel):
    account_id: str
    month: str
    net_deposit_krw: float


class ExternalNetWorthPoint(BaseModel):
    month: str
    total_krw: float


class ExternalAccountPerformance(BaseModel):
    xirr_pct: float | None = None
    current_value_krw: float
    net_invested_krw: float
    account_count: int
