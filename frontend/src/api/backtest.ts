import { apiDelete, apiGet, apiPost, apiPut } from "./client";

export interface HoldingItem {
  ticker: string;
  market: string;
  weight: number;
}

export interface BacktestPortfolioConfig {
  id: string;
  name: string;
  holdings: HoldingItem[];
  created_at: string;
  updated_at: string;
}

export interface BacktestRunRequest {
  portfolio_ids: string[];
  start_date: string;   // "YYYY-MM-DD"
  end_date: string;
  include_spy: boolean;
  include_real_portfolio: boolean;
  reinvest_dividends: boolean;
}

export interface SeriesData {
  name: string;
  values: (number | null)[];  // null = 해당 날짜 데이터 없음 (실제 포트폴리오 시작 전 구간)
}

export interface PortfolioMetrics {
  name: string;
  total_return_pct: number;
  cagr_pct: number;
  mdd_pct: number;
  sharpe_ratio: number;
  volatility_pct: number;
  sortino_ratio: number;
}

export interface BacktestResult {
  dates: string[];
  series: SeriesData[];
  metrics: PortfolioMetrics[];
}

export const fetchBacktestPortfolios = () =>
  apiGet<BacktestPortfolioConfig[]>("/backtest/portfolios");

export const createBacktestPortfolio = (body: { name: string; holdings: HoldingItem[] }) =>
  apiPost<BacktestPortfolioConfig>("/backtest/portfolios", body);

export const updateBacktestPortfolio = (
  id: string,
  body: { name?: string; holdings?: HoldingItem[] },
) => apiPut<BacktestPortfolioConfig>(`/backtest/portfolios/${id}`, body);

export const deleteBacktestPortfolio = (id: string) =>
  apiDelete(`/backtest/portfolios/${id}`);

export const runBacktest = (req: BacktestRunRequest) =>
  apiPost<BacktestResult>("/backtest/run", req);

export interface CorrelationRequest {
  portfolio_ids: string[];
  start_date: string;
  end_date: string;
}

export interface CorrelationResult {
  labels: string[];
  matrix: (number | null)[][];
}

export const runCorrelation = (req: CorrelationRequest) =>
  apiPost<CorrelationResult>("/backtest/correlation", req);
