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

export interface GoalAccelerationScenario {
  years_earlier: number;
  new_expected_goal_date: string;
  required_monthly_deposit: number;
  required_annual_deposit: number;
  extra_monthly_deposit: number;
  required_return_pct: number | null;
  extra_return_pct: number | null;
}

export interface GoalTimeline {
  months_to_goal: number | null;
  expected_goal_date: string | null;
  actual_expected_goal_date: string | null;
  current_progress_pct: number | null;
  on_track: boolean | null;
  lead_lag_months: number | null;
  acceleration_scenarios: GoalAccelerationScenario[];
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
  required_dividend_yield_pct: number | null;
  current_dividend_yield_pct: number | null;
  total_assets_krw: number;
  monthly_projected: MonthlyProjected[];
  monthly_received: { month: string; amount: number }[];
  yearly_received: YearlyReceived[];
}

export const fetchDividendPlan = () => apiGet<DividendPlanData>("/invest/dividend-plan");

export interface DepositGuideItem {
  annual_return_pct: number;
  required_monthly_deposit: number;
  required_annual_deposit: number;
}

export interface GoalFeasibilityPreview {
  required_return_pct: number | null;
  pv: number;
  n_months: number;
  note: string | null;
  deposit_guide: DepositGuideItem[];
}

export const fetchGoalFeasibility = (params: {
  goal_amount: number;
  target_year: number;
  monthly_deposit_amount?: number;
  initial_amount?: number;
}) => apiGet<GoalFeasibilityPreview>("/invest/goal-feasibility", { params });

// ── 달러 환전 계획(plans/96) — 예측이 아닌 1년 통계적 위치 + 해외 적립 필요 달러 분할 ──

export type FxZone = "CHEAP" | "NEUTRAL" | "EXPENSIVE";
export type FxPlanStatus = "OK" | "SUFFICIENT" | "NO_DEPOSIT_GOAL" | "NO_OVERSEAS" | "NO_PORTFOLIO";

export interface FxPosition {
  rate: number;
  low_1y: number;
  high_1y: number;
  /** 1년 종가 중 현재보다 낮았던 비율(%) — 낮을수록 달러가 싸다 */
  percentile_1y: number;
  ma20: number;
  ma60: number;
  deviation_ma20_pct: number;
  deviation_ma60_pct: number;
  sigma_1m: number;
  range_1m_low: number;
  range_1m_high: number;
  zone: FxZone;
}

export interface FxTranche {
  label: string;
  /** null = 지금(또는 적립일) 환전 */
  target_rate: number | null;
  usd: number;
  krw_estimate: number;
}

export interface FxPlanData {
  position: FxPosition | null;
  /** false = 실시간 환율이 없어 1년 일봉 마지막 종가 기준 */
  rate_is_live: boolean;
  status: FxPlanStatus;
  portfolio_id: string | null;
  portfolio_name: string | null;
  portfolio_options: { id: string; name: string }[];
  months: number;
  overseas_weight_pct: number;
  monthly_deposit_krw: number | null;
  monthly_need_usd: number;
  held_usd: number;
  need_usd: number;
  tranches: FxTranche[];
}

export const fetchFxPlan = (months: number, portfolioId?: string | null) => {
  const params = new URLSearchParams({ months: String(months) });
  if (portfolioId) params.set("portfolio_id", portfolioId);
  return apiGet<FxPlanData>(`/invest/fx-plan?${params.toString()}`);
};
