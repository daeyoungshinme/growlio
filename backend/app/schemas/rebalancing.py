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
    tax_type: str = "GENERAL"  # GENERAL | ISA | PENSION_SAVINGS | IRP | OVERSEAS_DEDICATED — 매도 계좌 우선순위에 사용


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
    is_tax_deferred: bool = False  # 매도 수량 중 일부/전부가 ISA·연금저축·IRP(과세이연) 계좌 보유분인 경우 True


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

    # 복합신호(시장 RED 또는 리스크 이상) — 진단탭 상단 배너와 동일 판정 함수(check_composite_signal) 결과.
    # True일 때는 market_note/risk_note를 생략해(위 필드가 None) 배너와 중복 문구를 표시하지 않는다.
    composite_signal_triggered: bool = False
    composite_signal_reason: str | None = None

    # 세금/거래비용 영향 미리보기 (diff_krw < 0 항목 기준 근사치)
    estimated_sell_realized_gain_krw: float = 0.0
    estimated_overseas_tax_krw: float = 0.0
    estimated_fee_krw: float = 0.0
    tax_notes: list[str] = []
    tax_detail_items: list[TaxImpactItem] = []  # 절대값 기준 상위 5개

    # 투자 목표 대비 비교 (UserSettings 미설정 시 None)
    goal_annual_return_pct: float | None = None
    goal_annual_dividend_krw: float | None = None


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


class QuickExecuteResult(BaseModel):
    """ "지금 테스트 실행" 결과 — AUTO와 동일하게 대기 플랜을 생성하고 이메일로 안내한다 (즉시 체결 아님)."""

    status: Literal["PLAN_GENERATED", "NO_DRIFT", "ALREADY_PENDING", "MARKET_BLOCKED"]
    message: str
    email_sent: bool = False
    plan_id: uuid.UUID | None = None
    buy_count: int = 0
    sell_count: int = 0


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
    triggered_by: str  # "MANUAL" | "AUTO"
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
    # AUTO 모드 매수 대기시간(분) — 플랜 이메일 발송 후 이 시간 뒤 자동 실행(취소 가능)
    buy_wait_minutes: int = 10

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

    @field_validator("buy_wait_minutes")
    @classmethod
    def validate_buy_wait_minutes(cls, v: int) -> int:
        if not (1 <= v <= 120):
            raise ValueError("매수 대기시간은 1~120분 사이여야 합니다")
        return v


class AlertScopeUpdate(BaseModel):
    alert_scope: Literal["AGGREGATE", "PER_ACCOUNT"]


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
    buy_wait_minutes: int
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ── 리밸런싱 대기 플랜 (AUTO 모드: 계획 생성 → 매수 대기/매도 승인) ──────────


class RebalancingPlanItemOut(BaseModel):
    ticker: str | None
    name: str | None
    market: str | None
    quantity: int
    account_id: str | None
    order_type: str
    limit_price: float | None
    reference_price: float | None

    model_config = {"from_attributes": True}


class RebalancingPlanLegSummary(BaseModel):
    plan_id: uuid.UUID
    leg_id: uuid.UUID
    portfolio_id: uuid.UUID | None
    portfolio_name: str | None
    account_id: uuid.UUID | None
    account_name: str | None
    side: Literal["BUY", "SELL"]
    status: Literal["PENDING", "EXECUTED", "CANCELED", "REJECTED", "EXPIRED", "FAILED"]
    deadline_at: datetime
    decided_at: datetime | None
    execution_id: uuid.UUID | None
    error_message: str | None
    actionable: bool  # status == PENDING and now < deadline_at
    items: list[RebalancingPlanItemOut]


class PlanActionResponse(BaseModel):
    status: str
    message: str


class SellDecisionRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]


class PlanTokenPreview(BaseModel):
    valid: bool
    reason: str | None = None  # "NOT_FOUND" | "ALREADY_DECIDED" | "EXPIRED"
    actionable: bool = False
    leg: RebalancingPlanLegSummary | None = None


class GoalRecommendationItem(BaseModel):
    ticker: str
    name: str
    market: str
    weight: float  # 0~100


class GoalRecommendation(BaseModel):
    """목표 역산 추천 — 로드맵 A 3단계. 자동 반영되지 않으며 사용자가 확인 후 수동 적용한다."""

    generated_at: str  # ISO timestamp
    is_configured: bool  # 목표금액/목표연도 미설정 시 False
    required_return_pct: float | None = None  # 목표 달성에 필요한 연평균 수익률(%)
    required_dividend_yield_pct: float | None = None  # 목표 배당 달성에 필요한 배당수익률(%, 현재 자산 기준)
    recommended_items: list[GoalRecommendationItem] = []
    expected_return_pct: float | None = None  # 추천 비중의 가중평균 CAGR(%) — cagr_lookback_years 기간 기준
    expected_dividend_yield_pct: float | None = None  # 추천 비중의 가중평균 배당수익률(%)
    note: str | None = None  # 미설정/이미 달성/달성 불가/리스크 성향 클램프 등 상태 설명
    cagr_lookback_years: int = 10  # 기대수익률(CAGR) 산출 기간(년) — 진단화면 10년 고정 지표와 다를 수 있음
    risk_tolerance: str = "CONSERVATIVE"  # 적용된 리스크 성향 (CONSERVATIVE/BALANCED/AGGRESSIVE)
    max_weight_pct: float = 40.0  # 적용된 종목당 최대 비중(%)


class CompositeSignalStatus(BaseModel):
    """진단탭 상단 복합신호(시장/리스크) 배너 — 유저 단위 단일 신호."""

    enabled: bool  # UserSettings.composite_signal_alerts_enabled
    triggered: bool  # enabled=True이고 조건(시장 RED 또는 리스크 이상) 충족 시 True
    reason: str | None = None
    has_active_alert: bool  # 활성 리밸런싱 알림이 1개라도 있는지 (없으면 enabled=True여도 실제 발송 안 됨)
