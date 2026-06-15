import { apiGet, apiPost } from "./client";

export interface DRIPYearlyPoint {
  year: number;
  portfolio_value_drip: number;
  portfolio_value_cash: number;
  cumulative_dividend_krw: number;
}

export interface DRIPSimulationResult {
  n_years: number;
  annual_return_pct: number;
  annual_dividend_yield_pct: number;
  initial_portfolio_value: number;
  monthly_contribution: number;
  final_value_drip: number;
  final_value_cash: number;
  drip_advantage_pct: number;
  total_dividend_received_krw: number;
  yearly_points: DRIPYearlyPoint[];
  note: string;
}

export interface MonthlyOptimizationItem {
  month: number;
  ticker: string;
  name: string;
  market: string;
  estimated_monthly_krw: number;
  current_monthly_total_krw: number;
}

export const fetchDRIPSimulation = (params: {
  n_years?: number;
  annual_dividend_yield_pct?: number;
}) => apiPost<DRIPSimulationResult>("/dividends/drip-simulation", params);

export const fetchMonthlyOptimization = () =>
  apiGet<MonthlyOptimizationItem[]>("/dividends/monthly-optimization");
