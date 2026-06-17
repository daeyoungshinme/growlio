import { apiGet } from "./client";

// ---------------------------------------------------------------------------
// 팩터 분석
// ---------------------------------------------------------------------------

export interface FactorHolding {
  ticker: string;
  name: string;
  weight_pct: number;
  pe_ratio: number | null;
  pb_ratio: number | null;
  market_cap: number | null;
  momentum_pct: number | null;
  value_score: number;
  growth_score: number;
  size_score: number;
  momentum_score: number;
}

export interface FactorAnalysis {
  holdings: FactorHolding[];
  portfolio_factors: {
    value: number;
    growth: number;
    size: number;
    momentum: number;
  };
  position_count: number;
  portfolio_name?: string;
  note: string;
}

// ---------------------------------------------------------------------------
// 효율적 프론티어
// ---------------------------------------------------------------------------

export interface FrontierPoint {
  risk: number;
  return: number;
}

export interface FrontierAsset {
  symbol: string;
  expected_return_pct: number;
  volatility_pct: number;
}

export interface EfficientFrontier {
  frontier: FrontierPoint[];
  current: FrontierPoint | null;
  target: FrontierPoint | null;
  assets: FrontierAsset[];
  note: string;
}

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

export interface CurrencyExposure {
  krw_value: number;
  usd_value: number;
  other_value: number;
  krw_pct: number;
  usd_pct: number;
  other_pct: number;
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
  apiGet<PortfolioRiskMetrics>(portfolioId ? `/portfolio/risk/${portfolioId}` : "/portfolio/risk");

export const fetchCurrencyExposure = () => apiGet<CurrencyExposure>("/portfolio/currency-exposure");

export const fetchFactorAnalysis = () => apiGet<FactorAnalysis>("/portfolio/factor-analysis");

export const fetchPortfolioFactorAnalysis = (portfolioId: string) =>
  apiGet<FactorAnalysis>(`/portfolio/factor-analysis/${portfolioId}`);

export const fetchEfficientFrontier = (comparePortfolioId?: string) =>
  apiGet<EfficientFrontier>(
    comparePortfolioId
      ? `/portfolio/efficient-frontier?compare_portfolio_id=${comparePortfolioId}`
      : "/portfolio/efficient-frontier",
  );

export const fetchRebalancingStrategy = (portfolioId: string) =>
  apiGet<RebalancingStrategy>(`/portfolio/rebalancing-strategy?portfolio_id=${portfolioId}`);
