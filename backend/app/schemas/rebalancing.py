"""리밸런싱 Pydantic 스키마."""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class TickerAccountInfo(BaseModel):
    account_id: str
    account_name: str
    asset_type: str  # "STOCK_KIS" | "STOCK_OTHER" | ...
    quantity: float = 0       # 해당 계좌 보유 수량
    value_krw: float = 0      # 해당 계좌 보유 금액 (KRW)
    is_mock_mode: bool = False  # KIS 모의 여부


class TargetPortfolioItem(BaseModel):
    ticker: str
    name: str
    market: str
    weight: float  # 0~100, 합계 = 100


class TargetPortfolioCreate(BaseModel):
    name: str
    items: list[TargetPortfolioItem]
    base_type: str = "STOCK_ONLY"  # STOCK_ONLY | TOTAL_ASSETS

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[TargetPortfolioItem]) -> list[TargetPortfolioItem]:
        if not v:
            raise ValueError("항목이 최소 1개 이상이어야 합니다.")
        total = sum(i.weight for i in v)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
        return v

    @field_validator("base_type")
    @classmethod
    def validate_base_type(cls, v: str) -> str:
        if v not in ("STOCK_ONLY", "TOTAL_ASSETS"):
            raise ValueError("base_type은 STOCK_ONLY 또는 TOTAL_ASSETS이어야 합니다.")
        return v


class TargetPortfolioUpdate(BaseModel):
    name: str | None = None
    items: list[TargetPortfolioItem] | None = None
    base_type: str | None = None

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: list[TargetPortfolioItem] | None) -> list[TargetPortfolioItem] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("항목이 최소 1개 이상이어야 합니다.")
        total = sum(i.weight for i in v)
        if abs(total - 100.0) > 0.01:
            raise ValueError(f"비중 합계가 100이어야 합니다. (현재: {total:.2f})")
        return v

    @field_validator("base_type")
    @classmethod
    def validate_base_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ("STOCK_ONLY", "TOTAL_ASSETS"):
            raise ValueError("base_type은 STOCK_ONLY 또는 TOTAL_ASSETS이어야 합니다.")
        return v


class TargetPortfolioResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    items: list[TargetPortfolioItem]
    base_type: str
    created_at: datetime
    updated_at: datetime


# ── 리밸런싱 분석 결과 ────────────────────────────────────────

class RebalancingItem(BaseModel):
    ticker: str
    name: str
    market: str
    target_weight_pct: float
    current_weight_pct: float
    weight_diff_pct: float       # target - current (양수=부족, 매수 필요)
    current_value_krw: float
    target_value_krw: float
    diff_krw: float              # 양수=매수, 음수=매도
    shares_to_trade: float | None  # CASH는 None
    current_price_krw: float | None
    dividend_yield: float | None = None          # % (2.5 = 2.5%)
    annual_dividend_current_krw: float = 0.0     # 현재 보유 기준 연간 배당금
    annual_dividend_target_krw: float = 0.0      # 목표 비중 기준 연간 배당금
    annual_dividend_diff_krw: float = 0.0        # 배당 증감 (target - current)
    return_10y_pct: float | None = None          # 10년 누적 수익률 (%)
    cagr_10y_pct: float | None = None            # 10년 연환산 수익률 (%)
    actual_years_10y: float | None = None        # 실제 데이터 기간 (년)


class CurrentHolding(BaseModel):
    """목표 포트폴리오에 없는 보유 종목."""
    ticker: str
    name: str
    market: str
    current_value_krw: float
    current_weight_pct: float


class RebalancingAnalysis(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_name: str
    base_type: str
    base_value_krw: float
    items: list[RebalancingItem]
    untracked_holdings: list[CurrentHolding]
    analyzed_at: str  # ISO timestamp
    current_portfolio_annual_dividend: float = 0.0   # 목표 포트폴리오 항목 기준 현재 연간 배당
    target_portfolio_annual_dividend: float = 0.0    # 목표 포트폴리오 연간 배당 합계
    total_current_annual_dividend: float = 0.0       # 미추적 종목 포함 전체 보유 기준 연간 배당
    target_weighted_cagr_10y_pct: float | None = None   # 목표 비중 기준 가중 CAGR (10년)
    current_weighted_cagr_10y_pct: float | None = None  # 현재 비중 기준 가중 CAGR (10년)
    ticker_account_map: dict[str, list[TickerAccountInfo]] = {}  # ticker → 보유 계좌 목록


# ── 리밸런싱 실행 ─────────────────────────────────────────────

class ExecutionOrderItem(BaseModel):
    ticker: str
    name: str
    market: str
    side: str           # "BUY" | "SELL"
    quantity: int       # 양수 (방향은 side로)
    account_id: str | None = None   # 실행할 KIS 계좌 ID (None이면 default_account_id 사용)


class ExecutionRequest(BaseModel):
    account_id: uuid.UUID | None = None   # 기본 KIS 계좌 (order에 account_id 없을 때 폴백)
    orders: list[ExecutionOrderItem]

    @field_validator("orders")
    @classmethod
    def validate_orders(cls, v: list[ExecutionOrderItem]) -> list[ExecutionOrderItem]:
        if not v:
            raise ValueError("주문 항목이 최소 1개 이상이어야 합니다.")
        return v


class KisBalancePosition(BaseModel):
    ticker: str
    name: str
    market: str
    quantity: int
    avg_price: float
    current_price: float
    value_krw: float


class KisBalanceResponse(BaseModel):
    account_id: str
    account_name: str
    is_mock: bool
    positions: list[KisBalancePosition]
    deposit_krw: float
    error: str | None = None  # 일괄 조회 시 계좌별 오류 메시지


class OrderResult(BaseModel):
    ticker: str
    name: str
    market: str
    side: str
    quantity: int
    status: str             # "SUCCESS" | "FAILED" | "SKIPPED"
    order_no: str | None = None
    error_msg: str | None = None


class ExecutionResult(BaseModel):
    account_id: str
    account_name: str
    is_mock: bool
    orders: list[OrderResult]
    success_count: int
    fail_count: int
    executed_at: str        # ISO timestamp
