import { api } from "./client";

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
}

export interface SeriesData {
  name: string;
  values: number[];
}

export interface PortfolioMetrics {
  name: string;
  total_return_pct: number;
  cagr_pct: number;
  mdd_pct: number;
  sharpe_ratio: number;
}

export interface BacktestResult {
  dates: string[];
  series: SeriesData[];
  metrics: PortfolioMetrics[];
}

export const fetchBacktestPortfolios = () =>
  api.get<BacktestPortfolioConfig[]>("/backtest/portfolios").then((r) => r.data);

export const createBacktestPortfolio = (body: { name: string; holdings: HoldingItem[] }) =>
  api.post<BacktestPortfolioConfig>("/backtest/portfolios", body).then((r) => r.data);

export const updateBacktestPortfolio = (
  id: string,
  body: { name?: string; holdings?: HoldingItem[] }
) => api.put<BacktestPortfolioConfig>(`/backtest/portfolios/${id}`, body).then((r) => r.data);

export const deleteBacktestPortfolio = (id: string) =>
  api.delete(`/backtest/portfolios/${id}`);

export const runBacktest = (req: BacktestRunRequest) =>
  api.post<BacktestResult>("/backtest/run", req).then((r) => r.data);
