import { api } from "./client";

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

export const fetchDCAAnalysis = () =>
  api.get<DCAAnalysisData>("/invest/dca-analysis").then((r) => r.data);
