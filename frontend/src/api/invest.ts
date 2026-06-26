import { apiGet } from "./client";

export interface DCAProjectionPoint {
  month: string;
  projected_krw: number;
  actual_krw: number | null;
  achievement_pct: number | null;
  has_data: boolean;
}

export interface YearlyAchievement {
  year: number;
  projected_year_end_krw: number;
  actual_year_end_krw: number | null;
  achievement_pct: number | null;
  has_data: boolean;
}

export interface GoalTimeline {
  months_to_goal: number | null;
  expected_goal_date: string | null;
  actual_expected_goal_date: string | null;
  current_progress_pct: number | null;
  on_track: boolean | null;
  lead_lag_months: number | null;
}

export interface DCASettings {
  monthly_deposit_amount: number | null;
  goal_annual_return_pct: number | null;
  goal_amount: number | null;
  goal_start_date: string | null;
  goal_initial_amount: number | null;
}

export interface DCAAnalysisData {
  settings: DCASettings;
  projection_months: DCAProjectionPoint[];
  yearly_achievements: YearlyAchievement[];
  goal_timeline: GoalTimeline;
  is_configured: boolean;
}

export const fetchDCAAnalysis = () => apiGet<DCAAnalysisData>("/invest/dca-analysis");

export interface MonthlyProjected {
  month: number;
  amount_krw: number;
}

export interface YearlyReceived {
  year: number;
  amount_krw: number;
}

export interface DividendPlanData {
  annual_dividend_goal: number | null;
  estimated_annual_krw: number;
  estimated_monthly_krw: number;
  actual_annual_received_krw: number;
  goal_achievement_pct: number | null;
  monthly_projected: MonthlyProjected[];
  monthly_received: { month: string; amount: number }[];
  yearly_received: YearlyReceived[];
}

export const fetchDividendPlan = () => apiGet<DividendPlanData>("/invest/dividend-plan");
