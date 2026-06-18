"""리밸런싱 Pydantic 스키마."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class TickerAccountInfo(BaseModel):
    account_id: str
    account_name: str
    asset_type: str  # "STOCK_KIS" | "STOCK_OTHER" | ...
    quantity: float = 0  # 해당 계좌 보유 수량
    value_krw: float = 0  # 해당 계좌 보유 금액 (KRW)
    is_mock_mode: bool = False  # KIS 모의 여부


# ── 리밸런싱 분석 결과 ────────────────────────────────────────


class RebalancingItem(BaseModel):
    ticker: str
    name: str
    market: str
    target_weight_pct: float
    current_weight_pct: float
    weight_diff_pct: float  # target - current (양수=부족, 매수 필요)
    current_value_krw: float
    target_value_krw: float
    diff_krw: float  # 양수=매수, 음수=매도
    shares_to_trade: float | None  # CASH는 None
    current_price_krw: float | None
    dividend_yield: float | None = None  # % (2.5 = 2.5%)
    annual_dividend_current_krw: float = 0.0  # 현재 보유 기준 연간 배당금
    annual_dividend_target_krw: float = 0.0  # 목표 비중 기준 연간 배당금
    annual_dividend_diff_krw: float = 0.0  # 배당 증감 (target - current)
    return_10y_pct: float | None = None  # 10년 누적 수익률 (%)
    cagr_10y_pct: float | None = None  # 10년 연환산 수익률 (%)
    actual_years_10y: float | None = None  # 실제 데이터 기간 (년)


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
    current_portfolio_annual_dividend: float = 0.0  # 목표 포트폴리오 항목 기준 현재 연간 배당
    target_portfolio_annual_dividend: float = 0.0  # 목표 포트폴리오 연간 배당 합계
    total_current_annual_dividend: float = 0.0  # 미추적 종목 포함 전체 보유 기준 연간 배당
    target_weighted_cagr_10y_pct: float | None = None  # 목표 비중 기준 가중 CAGR (10년)
    current_weighted_cagr_10y_pct: float | None = None  # 현재 비중 기준 가중 CAGR (10년)
    ticker_account_map: dict[str, list[TickerAccountInfo]] = {}  # ticker → 보유 계좌 목록
    available_cash_krw: float = 0.0  # 현재 예수금 (total_assets_krw - total_stock_krw)


# ── 리밸런싱 실행 ─────────────────────────────────────────────


class ExecutionOrderItem(BaseModel):
    ticker: str
    name: str
    market: str
    side: str  # "BUY" | "SELL"
    quantity: int  # 양수 (방향은 side로)
    account_id: str | None = None  # 실행할 KIS 계좌 ID (None이면 default_account_id 사용)
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    limit_price: float | None = None  # 국내=KRW 정수, 해외=USD 소수점 2자리

    @model_validator(mode="after")
    def validate_limit_price(self) -> "ExecutionOrderItem":
        if self.order_type == "LIMIT" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("지정가 주문에는 양수의 limit_price가 필요합니다.")
        return self


class ExecutionRequest(BaseModel):
    account_id: uuid.UUID | None = None  # 기본 KIS 계좌 (order에 account_id 없을 때 폴백)
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
    orderable_krw: float | None = None  # KIS만 지원 (nrcvb_buy_amt), 키움=None
    error: str | None = None  # 일괄 조회 시 계좌별 오류 메시지


# 키움 잔고 응답 — KIS와 동일한 구조
KiwoomBalanceResponse = KisBalanceResponse


class OrderResult(BaseModel):
    ticker: str
    name: str
    market: str
    side: str
    quantity: int
    status: str  # "SUCCESS" | "FAILED" | "SKIPPED"
    order_no: str | None = None
    error_msg: str | None = None
    order_type: str = "MARKET"


class ExecutionResult(BaseModel):
    account_id: str
    account_name: str
    is_mock: bool
    orders: list[OrderResult]
    success_count: int
    fail_count: int
    executed_at: str  # ISO timestamp


# ── 리밸런싱 실행 이력 ────────────────────────────────────────


class RebalancingExecutionSummary(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID | None
    triggered_by: str  # "MANUAL" | "AUTO" | "ONE_CLICK"
    strategy: str  # "FULL" | "BUY_ONLY"
    total_success: int
    total_fail: int
    total_skipped: int
    executed_at: datetime

    model_config = {"from_attributes": True}


class RebalancingExecutionDetail(RebalancingExecutionSummary):
    results: list[ExecutionResult] | None = None
