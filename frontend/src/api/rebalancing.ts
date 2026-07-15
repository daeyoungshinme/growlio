import { apiGet, apiPost } from "./client";
import type { GoalRiskTolerance } from "./settings";
import type { AccountTaxType } from "./assets";

export interface RebalancingItem {
  ticker: string;
  name: string;
  market: string;
  target_weight_pct: number;
  current_weight_pct: number;
  weight_diff_pct: number;
  current_value_krw: number;
  target_value_krw: number;
  diff_krw: number;
  shares_to_trade: number | null;
  current_price_krw: number | null;
  current_qty?: number | null;
  target_qty?: number | null;
  dividend_yield?: number | null;
  annual_dividend_current_krw?: number;
  annual_dividend_target_krw?: number;
  annual_dividend_diff_krw?: number;
  return_10y_pct?: number | null;
  cagr_10y_pct?: number | null;
  actual_years_10y?: number | null;
}

export interface CurrentHolding {
  ticker: string;
  name: string;
  market: string;
  current_value_krw: number;
  current_weight_pct: number;
}

export interface TickerAccountInfo {
  account_id: string;
  account_name: string;
  asset_type: string;
  quantity: number;
  value_krw: number;
  is_mock_mode: boolean;
}

export interface TaxImpactItem {
  ticker: string;
  name: string;
  market: string;
  is_overseas: boolean;
  sell_qty: number;
  estimated_realized_gain_krw: number;
  excluded_reason?: string | null;
  is_tax_deferred: boolean;
}

export interface DiagnosisContext {
  generated_at: string;
  market_level: "GREEN" | "YELLOW" | "RED" | null;
  market_note: string | null;
  risk_available: boolean;
  annualized_volatility_pct: number | null;
  beta_sp500: number | null;
  diversification_score: number | null;
  risk_note: string | null;
  composite_signal_triggered: boolean;
  composite_signal_reason: string | null;
  estimated_sell_realized_gain_krw: number;
  estimated_overseas_tax_krw: number;
  estimated_fee_krw: number;
  tax_notes: string[];
  tax_detail_items: TaxImpactItem[];
  goal_annual_return_pct: number | null;
  goal_annual_dividend_krw: number | null;
}

export interface RebalancingAnalysis {
  portfolio_id: string;
  portfolio_name: string;
  base_type: string;
  base_value_krw: number;
  items: RebalancingItem[];
  untracked_holdings: CurrentHolding[];
  analyzed_at: string;
  current_portfolio_annual_dividend: number;
  target_portfolio_annual_dividend: number;
  total_current_annual_dividend?: number;
  target_weighted_cagr_10y_pct?: number | null;
  current_weighted_cagr_10y_pct?: number | null;
  ticker_account_map: Record<string, TickerAccountInfo[]>;
  available_cash_krw?: number;
  diagnosis_context?: DiagnosisContext | null;
}

export const analyzePortfolio = (
  id: string,
  accountIds?: string[],
  depositKrwOverride?: number,
) => {
  const params = new URLSearchParams();
  if (accountIds?.length) {
    for (const aid of accountIds) params.append("account_ids", aid);
  }
  if (depositKrwOverride !== undefined) {
    params.append("deposit_krw_override", String(Math.round(depositKrwOverride)));
  }
  return apiGet<RebalancingAnalysis>(`/rebalancing/portfolios/${id}/analyze`, {
    params: params.size > 0 ? params : undefined,
  });
};

// ── 리밸런싱 실행 ─────────────────────────────────────────────

export interface ExecutionOrderItem {
  ticker: string;
  name: string;
  market: string;
  side: "BUY" | "SELL";
  quantity: number;
  account_id?: string | null;
  order_type: "MARKET" | "LIMIT";
  limit_price?: number | null; // 국내=KRW, 해외=USD
}

export interface ExecutionRequest {
  account_id?: string | null;
  orders: ExecutionOrderItem[];
  strategy?: "FULL" | "BUY_ONLY" | "TWO_PHASE";
}

export interface OrderResult {
  ticker: string;
  name: string;
  market: string;
  side: "BUY" | "SELL";
  quantity: number;
  status: "SUCCESS" | "FAILED" | "SKIPPED";
  order_no: string | null;
  error_msg: string | null;
  order_type?: string;
  price?: number | null;
}

export interface ExecutionResult {
  account_id: string;
  account_name: string;
  is_mock: boolean;
  orders: OrderResult[];
  success_count: number;
  fail_count: number;
  executed_at: string;
}

export const executeRebalancing = (
  portfolioId: string,
  body: ExecutionRequest,
): Promise<ExecutionResult[]> =>
  apiPost<ExecutionResult[]>(`/rebalancing/portfolios/${portfolioId}/execute`, body);

// ── KIS 실시간 잔고 조회 ──────────────────────────────────────

export interface KisBalancePosition {
  ticker: string;
  name: string;
  market: string;
  quantity: number;
  avg_price: number;
  current_price: number;
  value_krw: number;
}

export interface KisBalanceResponse {
  account_id: string;
  account_name: string;
  is_mock: boolean;
  positions: KisBalancePosition[];
  deposit_krw: number;
  orderable_krw: number | null;
  error?: string | null;
}

export const fetchBrokerBalance = (accountId: string): Promise<KisBalanceResponse> =>
  apiGet<KisBalanceResponse>(`/rebalancing/broker-balance/${accountId}`);

export const fetchAllBrokerBalances = (): Promise<KisBalanceResponse[]> =>
  apiGet<KisBalanceResponse[]>(`/rebalancing/broker-balance-all`);

// ── 지금 테스트 실행 (대기 플랜 생성 + 이메일 발송, AUTO와 동일 파이프라인) ──────────

export interface QuickExecuteOverride {
  account_id?: string | null;
  strategy?: "FULL" | "BUY_ONLY" | "TWO_PHASE";
  order_type?: "MARKET" | "LIMIT";
}

export interface QuickExecuteResult {
  status: "PLAN_GENERATED" | "NO_DRIFT" | "ALREADY_PENDING" | "MARKET_BLOCKED";
  message: string;
  email_sent: boolean;
  plan_id: string | null;
  buy_count: number;
  sell_count: number;
}

export const quickExecuteRebalancing = (
  portfolioId: string,
  override?: QuickExecuteOverride,
  /** PER_ACCOUNT 스코프 포트폴리오는 어느 계좌 전용 알림 행을 실행할지 지정해야 한다. */
  scopeAccountId?: string,
): Promise<QuickExecuteResult> =>
  apiPost<QuickExecuteResult>(`/rebalancing/portfolios/${portfolioId}/quick-execute`, override, {
    params: scopeAccountId ? { account_id: scopeAccountId } : undefined,
  });

// ── 실행 이력 ──────────────────────────────────────────────

export interface RebalancingExecutionSummary {
  id: string;
  portfolio_id: string | null;
  triggered_by: "MANUAL" | "AUTO";
  strategy: "FULL" | "BUY_ONLY" | "TWO_PHASE";
  total_success: number;
  total_fail: number;
  total_skipped: number;
  executed_at: string;
}

export interface RebalancingExecutionDetail extends RebalancingExecutionSummary {
  results: ExecutionResult[] | null;
}

export const fetchRebalancingHistory = (limit = 20): Promise<RebalancingExecutionSummary[]> =>
  apiGet<RebalancingExecutionSummary[]>(`/rebalancing/history`, { params: { limit } });

export const fetchRebalancingExecutionDetail = (id: string): Promise<RebalancingExecutionDetail> =>
  apiGet<RebalancingExecutionDetail>(`/rebalancing/history/${id}`);

// ── 드리프트 요약 (대시보드용 경량 조회) ────────────────────────

export interface DriftedItem {
  ticker: string;
  name: string;
  weight_diff_pct: number;
}

export interface PortfolioDriftSummary {
  portfolio_id: string;
  portfolio_name: string;
  needs_rebalancing: boolean;
  threshold_pct: number;
  max_drift_pct: number;
  drifted_items_count: number;
  top_drifted_items: DriftedItem[];
  has_composite_signal?: boolean;
  composite_reason?: string | null;
  has_alert_configured?: boolean;
}

export const fetchDriftSummary = (): Promise<PortfolioDriftSummary[]> =>
  apiGet<PortfolioDriftSummary[]>(`/rebalancing/drift-summary`);

// ── 복합신호(시장/리스크) 상태 (진단탭 상단 배너 전용, 유저 단위) ────────────

export interface CompositeSignalStatus {
  enabled: boolean;
  triggered: boolean;
  reason: string | null;
  has_active_alert: boolean;
}

export const fetchCompositeSignalStatus = (): Promise<CompositeSignalStatus> =>
  apiGet<CompositeSignalStatus>(`/rebalancing/composite-signal`);

// ── 목표 역산 추천 (로드맵 A 3단계) ──────────────────────────────

export interface GoalRecommendationItem {
  ticker: string;
  name: string;
  market: string;
  weight: number;
}

export interface GoalRecommendation {
  generated_at: string;
  is_configured: boolean;
  required_return_pct: number | null;
  required_dividend_yield_pct: number | null;
  recommended_items: GoalRecommendationItem[];
  expected_return_pct: number | null;
  expected_dividend_yield_pct: number | null;
  note: string | null;
  cagr_lookback_years: number;
  risk_tolerance: GoalRiskTolerance;
  max_weight_pct: number;
}

export const fetchOverallGoalRecommendation = (): Promise<GoalRecommendation> =>
  apiGet<GoalRecommendation>(`/rebalancing/goal-recommendation`);

// ── 투자기간별(단기/중기/장기) 추천 — 목표 역산이 아닌 리스크 성향 재배분 ──────

/** 단일 소스는 @/constants/assets — 포트폴리오 편집기의 CASH_EQUIVALENT 항목과 동일 식별자를 공유한다. */
export { CASH_EQUIVALENT_TICKER } from "@/constants/assets";

export interface HorizonGoalRecommendation {
  investment_horizon: "SHORT_TERM" | "MID_TERM" | "LONG_TERM";
  tax_type: AccountTaxType;
  base_krw: number;
  account_count: number;
  recommended_items: GoalRecommendationItem[];
  expected_return_pct: number | null;
  risk_tolerance: GoalRiskTolerance;
  max_weight_pct: number;
  includes_cash_equivalent: boolean;
  note: string | null;
}

export interface HorizonRecommendationResponse {
  generated_at: string;
  recommendations: HorizonGoalRecommendation[];
}

export const fetchHorizonGoalRecommendations = (): Promise<HorizonRecommendationResponse> =>
  apiGet<HorizonRecommendationResponse>(`/rebalancing/goal-recommendation/by-horizon`);
