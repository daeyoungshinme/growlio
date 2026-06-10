import { api } from "@/api/client";

export interface MarketIndexItem {
  symbol: string;
  name: string;
  price: number | null;
  change_pct: number | null;
  week_change_pct: number | null;
}

export interface ExchangeRateInfo {
  usd_krw: number | null;
  change_pct: number | null;
}

export interface SectorInfo {
  sector: string;
  etf_ticker: string;
  change_pct: number | null;
}

export interface PortfolioRisk {
  score: number;
  concentration_risk: string;
  sector_bias: string[];
  description: string;
}

export interface RecommendedAction {
  ticker: string;
  name: string;
  action: string;
  reason: string;
  priority: string;
}

export interface AlternativePortfolioItem {
  ticker: string;
  name: string;
  weight: number;
  reason: string;
}

export interface AlternativePortfolio {
  risk_level: string;
  expected_return: string;
  items: AlternativePortfolioItem[];
}

export interface AIAnalysisResult {
  market_summary: string;
  portfolio_risk: PortfolioRisk;
  recommendations: RecommendedAction[];
  alternative_portfolios: AlternativePortfolio[];
  disclaimer: string;
}

export interface AIAnalysisResponse {
  status: "ready" | "error";
  cached_at: string | null;
  market_indices: MarketIndexItem[];
  exchange_rate: ExchangeRateInfo;
  sector_performance: SectorInfo[];
  analysis: AIAnalysisResult | null;
  error_message: string | null;
}

export const fetchAIAnalysis = (forceRefresh = false) =>
  api
    .get<AIAnalysisResponse>("/ai-analysis", { params: { force_refresh: forceRefresh } })
    .then((r) => r.data);
