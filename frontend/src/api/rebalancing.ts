import { api } from "./client";

export interface TargetPortfolioItem {
  ticker: string;
  name: string;
  market: string;
  weight: number;
}

export interface TargetPortfolio {
  id: string;
  name: string;
  items: TargetPortfolioItem[];
  base_type: string;
  created_at: string;
  updated_at: string;
}

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
}

export const fetchTargetPortfolios = () =>
  api.get<TargetPortfolio[]>("/rebalancing/portfolios").then((r) => r.data);

export const createTargetPortfolio = (body: {
  name: string;
  items: TargetPortfolioItem[];
  base_type: string;
}) => api.post<TargetPortfolio>("/rebalancing/portfolios", body).then((r) => r.data);

export const updateTargetPortfolio = (
  id: string,
  body: { name?: string; items?: TargetPortfolioItem[]; base_type?: string }
) => api.put<TargetPortfolio>(`/rebalancing/portfolios/${id}`, body).then((r) => r.data);

export const deleteTargetPortfolio = (id: string) =>
  api.delete(`/rebalancing/portfolios/${id}`);

export const analyzePortfolio = (id: string) =>
  api.get<RebalancingAnalysis>(`/rebalancing/portfolios/${id}/analyze`).then((r) => r.data);

// ── 리밸런싱 실행 ─────────────────────────────────────────────

export interface ExecutionOrderItem {
  ticker: string;
  name: string;
  market: string;
  side: "BUY" | "SELL";
  quantity: number;
}

export interface ExecutionRequest {
  account_id: string;
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

export const executeRebalancing = (portfolioId: string, body: ExecutionRequest): Promise<ExecutionResult> =>
  api.post<ExecutionResult>(`/rebalancing/portfolios/${portfolioId}/execute`, body).then((r) => r.data);
