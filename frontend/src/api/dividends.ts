import { apiGet } from "./client";
import type { DividendByTicker, DividendYield } from "@/types";

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

export interface DividendSummary {
  annual_received: number;
  estimated_annual: number;
  monthly_breakdown: { month: string; amount: number }[];
  monthly_ticker_breakdown: { month: string; ticker: string | null; amount: number }[];
}

const accountParams = (accountId?: string | null) => ({
  params: { account_id: accountId || undefined },
});

export const fetchDividendPositions = (accountId?: string | null) =>
  apiGet<DividendYield[]>("/dividends/positions", accountParams(accountId));

export const fetchDividendSummary = (accountId?: string | null) =>
  apiGet<DividendSummary>("/dividends/summary", accountParams(accountId));

export const fetchDividendByTicker = (accountId?: string | null) =>
  apiGet<DividendByTicker[]>("/dividends/by-ticker", accountParams(accountId));
