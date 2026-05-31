import { api } from "./client";

export interface AllocationItem {
  type: string;
  amount_krw: number;
  pct: number;
}

export interface MonthlyTrend {
  month: string;
  total_krw: number;
}

export interface DividendMonthlyBreakdown {
  month: string;
  amount: number;
}

export interface DashboardData {
  total_assets_krw: number;
  asset_allocation: AllocationItem[];
  goal_amount: number | null;
  goal_achievement_pct: number | null;
  stock_return_pct: number;
  annual_return_pct: number | null;
  monthly_trend: MonthlyTrend[];
  annual_deposit_goal: number | null;
  deposit_achievement_pct: number | null;
  annual_dividends_received: number | null;
  estimated_annual_dividends: number | null;
  dividend_monthly_breakdown: DividendMonthlyBreakdown[];
  cumulative_return_pct: number | null;
  xirr_pct: number | null;
  benchmark_kospi_pct: number | null;
  benchmark_sp500_pct: number | null;
  goal_annual_return_pct: number | null;
  retirement_target_year: number | null;
}

export const fetchDashboard = () =>
  api.get<DashboardData>("/dashboard").then((r) => r.data);

export interface TickerDividendItem {
  ticker: string | null;
  name: string;
  market: string | null;
  received_krw: number;
  estimated_annual_krw: number;
  estimated_monthly_krw: number;
  dividend_yield: number;
  dps: number;
  dividend_months: number[];
  dividend_months_is_manual: boolean;
  investment_yield: number;
  currency: string;
  estimated_monthly_usd: number | null;
}

export const fetchDividendByTicker = () =>
  api.get<TickerDividendItem[]>("/dividends/by-ticker").then((r) => r.data);

export const updateTickerDividendMonths = (ticker: string, market: string, dividend_months: number[]) =>
  api.put(`/dividends/ticker-settings/${ticker}`, { market, dividend_months }).then((r) => r.data);

export const deleteTickerDividendMonths = (ticker: string, market: string) =>
  api.delete(`/dividends/ticker-settings/${ticker}`, { params: { market } }).then((r) => r.data);
