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
    current_qty: float | None = None  # 현재 보유 수량
    target_qty: float | None = None  # 목표 수량 (현재가 기준)
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


class TaxImpactItem(BaseModel):
    """세금 영향 미리보기 — 매도 대상 종목별 추정치(근사치, 참고용)."""

    ticker: str
    name: str
    market: str
    is_overseas: bool
    sell_qty: float
    estimated_realized_gain_krw: float  # 양수=이익, 음수=손실
    excluded_reason: str | None = None  # 가격/평단가 부족 등으로 추정 제외 시 사유


class DiagnosisContext(BaseModel):
    """리밸런싱 진단 화면 부가 설명.

    needs_rebalancing 판정/알림 트리거 로직과는 별개 — 화면 설명 전용 정보다.
    외부 API 조회 실패 시 해당 필드만 None/False로 안전하게 누락 처리된다.
    """

    generated_at: str  # ISO timestamp

    # 시장 상황
    market_level: Literal["GREEN", "YELLOW", "RED"] | None = None
    market_note: str | None = None

    # 리스크 지표 (전체 계좌 기준 — RiskMetricsCard와 동일 캐시 재사용)
    risk_available: bool = False
    annualized_volatility_pct: float | None = None
    beta_sp500: float | None = None
    diversification_score: int | None = None
    risk_note: str | None = None  # 특이사항 없으면 None (조용히 생략)

    # 세금/거래비용 영향 미리보기 (diff_krw < 0 항목 기준 근사치)
    estimated_sell_realized_gain_krw: float = 0.0
    estimated_overseas_tax_krw: float = 0.0
    estimated_fee_krw: float = 0.0
    tax_notes: list[str] = []
    tax_detail_items: list[TaxImpactItem] = []  # 절대값 기준 상위 5개


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
    available_cash_krw: float = 0.0  # 현재 예수금 (account.deposit_krw 합산; fallback: total_assets - total_stock)
    diagnosis_context: DiagnosisContext | None = None  # 시장상황·리스크·세금 부가 설명 (실패 시 None)


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
    reference_price: float | None = None  # 주문 생성 시점 조회한 참고 시세(표시 전용, 브로커 API에는 전달 안 됨)

    @model_validator(mode="after")
    def validate_limit_price(self) -> "ExecutionOrderItem":
        if self.order_type == "LIMIT" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("지정가 주문에는 양수의 limit_price가 필요합니다.")
        return self


class ExecutionRequest(BaseModel):
    account_id: uuid.UUID | None = None  # 기본 KIS 계좌 (order에 account_id 없을 때 폴백)
    orders: list[ExecutionOrderItem]
    strategy: Literal["FULL", "BUY_ONLY", "TWO_PHASE"] = "FULL"

    @field_validator("orders")
    @classmethod
    def validate_orders(cls, v: list[ExecutionOrderItem]) -> list[ExecutionOrderItem]:
        if not v:
            raise ValueError("주문 항목이 최소 1개 이상이어야 합니다.")
        return v


class QuickExecuteOverride(BaseModel):
    """원클릭 실행(quick-execute) 시 저장된 알림 설정 대신 사용할 화면 값 override."""

    account_id: uuid.UUID | None = None
    strategy: Literal["FULL", "BUY_ONLY", "TWO_PHASE"] | None = None
    order_type: Literal["MARKET", "LIMIT"] | None = None


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
    price: float | None = None  # 지정가 또는 주문 생성 시점 참고 시세 (국내=KRW, 해외=USD)


class ExecutionResult(BaseModel):
    account_id: str
    account_name: str
    is_mock: bool
    orders: list[OrderResult]
    success_count: int
    fail_count: int
    executed_at: str  # ISO timestamp


# ── 드리프트 요약 (대시보드용 경량 조회) ────────────────────────


class DriftedItem(BaseModel):
    ticker: str
    name: str
    weight_diff_pct: float  # 양수=매수 필요, 음수=매도 필요


class PortfolioDriftSummary(BaseModel):
    portfolio_id: uuid.UUID
    portfolio_name: str
    needs_rebalancing: bool
    threshold_pct: float  # 알림 임계값 (없으면 기본값 5.0)
    max_drift_pct: float  # 이탈 종목 중 최대 |weight_diff_pct|
    drifted_items_count: int  # threshold를 초과한 종목 수
    top_drifted_items: list[DriftedItem]  # 이탈 크기 상위 3개
    has_composite_signal: bool = False  # drift는 없지만 리스크/시장 신호로 점검을 권장하는 경우
    composite_reason: str | None = None  # has_composite_signal=True일 때 사유 문구
    has_alert_configured: bool = False  # 활성 RebalancingAlert 설정 여부 (없으면 이 포트폴리오는 알림이 발송되지 않음)


# ── 리밸런싱 실행 이력 ────────────────────────────────────────


class RebalancingExecutionSummary(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID | None
    triggered_by: str  # "MANUAL" | "AUTO" | "ONE_CLICK"
    strategy: str  # "FULL" | "BUY_ONLY" | "TWO_PHASE"
    total_success: int
    total_fail: int
    total_skipped: int
    executed_at: datetime

    model_config = {"from_attributes": True}


class RebalancingExecutionDetail(RebalancingExecutionSummary):
    results: list[ExecutionResult] | None = None


# ── 리밸런싱 알림 설정 ────────────────────────────────────────


class RebalancingAlertCreate(BaseModel):
    portfolio_id: uuid.UUID
    threshold_pct: float = 5.0
    schedule_type: Literal["DAILY", "WEEKLY", "MONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"] = "DAILY"
    schedule_day_of_week: int | None = None  # WEEKLY 전용: 0=월...6=일
    schedule_day_of_month: int | None = None  # MONTHLY/QUARTERLY/SEMIANNUAL/ANNUAL: 1~28
    trigger_condition: Literal["DRIFT_ONLY", "SCHEDULE_ONLY", "BOTH"] = "DRIFT_ONLY"
    mode: Literal["NOTIFY", "AUTO"] = "NOTIFY"
    strategy: Literal["FULL", "BUY_ONLY", "TWO_PHASE"] = "BUY_ONLY"
    account_id: uuid.UUID | None = None
    order_type: Literal["MARKET", "LIMIT"] = "MARKET"
    market_condition_mode: Literal["DISABLED", "CAUTIOUS", "STRICT"] = "DISABLED"
    # AUTO 모드 실행 시각 (HH:MM KST, 예: "09:30"). None이면 장 개시 후 첫 tick에 실행
    auto_execution_time: str | None = None
    # NOTIFY 모드 알림 발송 시각 (HH:MM KST, 기본: "08:30")
    notify_time: str = "08:30"
    # drift가 없어도 리스크 집중/시장 위험 신호가 있으면 추가로 발송 (기본 True, AUTO 실행에는 영향 없음)
    enable_composite_signals: bool = True

    @field_validator("threshold_pct")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        if not (0.1 <= v <= 50.0):
            raise ValueError("임계값은 0.1%에서 50% 사이여야 합니다")
        return round(v, 2)

    @field_validator("schedule_day_of_week")
    @classmethod
    def validate_dow(cls, v: int | None) -> int | None:
        if v is not None and not (0 <= v <= 6):
            raise ValueError("요일은 0(월)~6(일) 사이여야 합니다")
        return v

    @field_validator("schedule_day_of_month")
    @classmethod
    def validate_dom(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 28):
            raise ValueError("날짜는 1~28 사이여야 합니다")
        return v

    @field_validator("auto_execution_time")
    @classmethod
    def validate_auto_execution_time(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            hh, mm = v.split(":")
            hour, minute = int(hh), int(mm)
        except (ValueError, AttributeError):
            raise ValueError("실행 시각은 HH:MM 형식이어야 합니다 (예: 09:30)") from None
        if not (9 <= hour <= 15) or not (0 <= minute <= 59):
            raise ValueError("실행 시각은 09:00~15:00 KST 범위여야 합니다")
        return f"{hour:02d}:{minute:02d}"

    @field_validator("notify_time")
    @classmethod
    def validate_notify_time(cls, v: str) -> str:
        try:
            hh, mm = v.split(":")
            hour, minute = int(hh), int(mm)
        except (ValueError, AttributeError):
            raise ValueError("알림 시각은 HH:MM 형식이어야 합니다 (예: 08:30)") from None
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ValueError("알림 시각은 00:00~23:59 범위여야 합니다")
        return f"{hour:02d}:{minute:02d}"


class TestAlertResponse(BaseModel):
    email_sent: bool
    push_sent: bool
    message: str


class RebalancingAlertResponse(BaseModel):
    id: uuid.UUID
    portfolio_id: uuid.UUID
    is_active: bool
    threshold_pct: float
    schedule_type: str
    schedule_day_of_week: int | None
    schedule_day_of_month: int | None
    trigger_condition: str
    mode: str
    strategy: str
    account_id: uuid.UUID | None
    order_type: str
    market_condition_mode: str
    auto_execution_time: str | None
    notify_time: str
    enable_composite_signals: bool = True
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime
