import { apiGet } from "./client";

export interface MonthlyOptimizationItem {
  month: number;
  ticker: string;
  name: string;
  market: string;
  estimated_monthly_krw: number;
  current_monthly_total_krw: number;
}

export const fetchMonthlyOptimization = () =>
  apiGet<MonthlyOptimizationItem[]>("/dividends/monthly-optimization");
