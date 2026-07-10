import { apiGet } from "./client";

// ---------------------------------------------------------------------------
// 위험 지표 (기존)
// ---------------------------------------------------------------------------

export interface PortfolioRiskMetrics {
  var_95_pct: number;
  var_99_pct: number;
  annualized_volatility_pct: number;
  beta_sp500: number;
  diversification_score: number;
  top_holding_weight_pct: number;
  position_count: number;
  data_available: boolean;
  note: string;
}

// ---------------------------------------------------------------------------
// 리밸런싱 전략
// ---------------------------------------------------------------------------

export interface FactorChange {
  current: number;
  target: number;
  delta: number;
}

export interface FrontierChanges {
  current_risk: number | null;
  current_return: number | null;
  target_risk: number | null;
  target_return: number | null;
  risk_change: number | null;
  return_change: number | null;
  sharpe_improvement: boolean | null;
  current_sharpe: number | null;
  target_sharpe: number | null;
}

export interface TradeRecommendation {
  action: string;
  ticker: string;
  market: string;
  name: string;
  current_weight: number;
  target_weight: number;
  reason: string;
}

export interface RebalancingStrategy {
  portfolio_id: string;
  portfolio_name: string;
  factor_changes: Record<string, FactorChange>;
  frontier_changes: FrontierChanges;
  trade_recommendations: TradeRecommendation[];
  overall_direction: string;
  summary: string;
}

// ---------------------------------------------------------------------------
// API 함수
// ---------------------------------------------------------------------------

export const fetchPortfolioRisk = (portfolioId?: string) =>
  apiGet<PortfolioRiskMetrics>(
    "/portfolio/risk",
    portfolioId ? { params: { portfolio_id: portfolioId } } : undefined,
  );

export const fetchRebalancingStrategy = (portfolioId: string) =>
  apiGet<RebalancingStrategy>(`/portfolio/rebalancing-strategy?portfolio_id=${portfolioId}`);
