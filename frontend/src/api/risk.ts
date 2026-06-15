import { apiGet } from "./client";

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
