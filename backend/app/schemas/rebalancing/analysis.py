"""리밸런싱 분석 결과 스키마."""

import uuid
from typing import Literal

from pydantic import BaseModel


class TickerAccountInfo(BaseModel):
    account_id: str
    account_name: str
    asset_type: str  # "STOCK_KIS" | "STOCK_OTHER" | ...
    quantity: float = 0  # 해당 계좌 보유 수량
    value_krw: float = 0  # 해당 계좌 보유 금액 (KRW)
    is_mock_mode: bool = False  # KIS 모의 여부
    tax_type: str = "GENERAL"  # GENERAL | ISA | PENSION_SAVINGS | IRP | OVERSEAS_DEDICATED — 매도 계좌 우선순위에 사용


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
