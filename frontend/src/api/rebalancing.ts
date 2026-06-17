import { apiGet, apiPost } from "./client";

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
}

export const analyzePortfolio = (id: string, accountIds?: string[]) => {
  const params = new URLSearchParams();
  if (accountIds?.length) {
    for (const aid of accountIds) params.append("account_ids", aid);
  }
  return apiGet<RebalancingAnalysis>(`/rebalancing/portfolios/${id}/analyze`, {
    params: accountIds?.length ? params : undefined,
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

// ── 원클릭 실행 ──────────────────────────────────────────────

export const quickExecuteRebalancing = (portfolioId: string): Promise<ExecutionResult[]> =>
  apiPost<ExecutionResult[]>(`/rebalancing/portfolios/${portfolioId}/quick-execute`);

// ── 실행 이력 ──────────────────────────────────────────────

export interface RebalancingExecutionSummary {
  id: string;
  portfolio_id: string | null;
  triggered_by: "MANUAL" | "AUTO" | "ONE_CLICK";
  strategy: "FULL" | "BUY_ONLY";
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
