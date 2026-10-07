import { apiPost } from "./client";

export interface BacktestRunRequest {
  portfolio_ids: string[];
  start_date: string; // "YYYY-MM-DD"
  end_date: string;
  include_spy: boolean;
  include_real_portfolio: boolean;
  reinvest_dividends: boolean;
}

export interface SeriesData {
  name: string;
  values: (number | null)[]; // null = 해당 날짜 데이터 없음 (실제 포트폴리오 시작 전 구간)
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

export const runBacktest = (req: BacktestRunRequest) =>
  apiPost<BacktestResult>("/backtest/run", req);
