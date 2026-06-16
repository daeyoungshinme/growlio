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

export const fetchPortfolioRisk = (portfolioId?: string) =>
  apiGet<PortfolioRiskMetrics>(
    portfolioId ? `/portfolio/risk/${portfolioId}` : "/portfolio/risk",
  );

export const fetchCurrencyExposure = () =>
  apiGet<CurrencyExposure>("/portfolio/currency-exposure");

export const fetchFactorAnalysis = () =>
  apiGet<FactorAnalysis>("/portfolio/factor-analysis");

export const fetchEfficientFrontier = () =>
  apiGet<EfficientFrontier>("/portfolio/efficient-frontier");
