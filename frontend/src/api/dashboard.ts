import { apiGet } from "./client";
import type { ActionPriority } from "@/utils/actionPriority";

export interface DashboardAllocationItem {
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
  asset_allocation: DashboardAllocationItem[];
  goal_amount: number | null;
  goal_achievement_pct: number | null;
  stock_return_pct: number;
  annual_return_pct: number | null;
  monthly_trend: MonthlyTrend[];
  annual_deposit_goal: number | null;
  annual_deposit_current: number;
  deposit_achievement_pct: number | null;
  annual_dividends_received: number | null;
  estimated_annual_dividends: number | null;
  dividend_monthly_breakdown: DividendMonthlyBreakdown[];
  cumulative_return_pct: number | null;
  xirr_pct: number | null;
  xirr_is_estimated: boolean;
  goal_annual_return_pct: number | null;
  return_goal_gap_pct: number | null;
  retirement_target_year: number | null;
  annual_dividend_goal: number | null;
  dividend_goal_achievement_pct: number | null;
}

export const fetchDashboard = () => apiGet<DashboardData>("/dashboard");

export type ActionItemKind =
  "REBALANCE" | "DCA_SHORTFALL" | "TAX_WARNING" | "TAX_ACTION" | "CHALLENGE";

/** 홈 "지금 할 일" 1행 — 백엔드 `action_items_service`가 우선순위·마감 순으로 최대 5건 반환 */
export interface ActionItem {
  id: string;
  kind: ActionItemKind;
  priority: ActionPriority;
  title: string;
  detail: string;
  cta_label: string;
  link: string;
  deadline: string | null;
}

export const fetchActionItems = () => apiGet<ActionItem[]>("/dashboard/action-items");
