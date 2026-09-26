import { apiGet, apiPut } from "./client";

export type AssetClass = "EQUITY" | "BOND" | "CASH";

export type IndexRegion = "DOMESTIC" | "OVERSEAS";

export interface GoalCandidateTicker {
  ticker: string;
  name: string;
  market: string;
  asset_class?: AssetClass;
  index_region?: IndexRegion | null;
}

export type GoalRiskTolerance = "CONSERVATIVE" | "BALANCED" | "AGGRESSIVE";

export type AgeGroup = "TWENTIES" | "THIRTIES" | "FORTIES" | "FIFTIES" | "SIXTIES_PLUS";

/** 연금 세액공제율 분기 — 총급여 5,500만원 이하 16.5% / 초과 13.2% (금액은 저장하지 않음) */
export type IncomeBracket = "UNDER_55M" | "OVER_55M";

export interface GoalRecommendationOptions {
  risk_tolerance: GoalRiskTolerance;
  max_weight_pct: number;
  cagr_lookback_years: number;
  short_term_equity_floor_pct: number;
  age_group: AgeGroup | null;
  bond_ceiling_pct: number | null;
  cash_ceiling_pct: number | null;
}

export interface SettingsData {
  has_kis: boolean;
  has_dart: boolean;
  goal_amount: number | null;
  goal_annual_return_pct: number | null;
  annual_deposit_goal: number | null;
  monthly_deposit_amount: number | null;
  retirement_target_year: number | null;
  user_email: string;
  notification_email: string | null;
  annual_dividend_goal: number | null;
  fcm_token_stored: boolean;
  composite_signal_alerts_enabled: boolean;
  market_signal_daily_digest_enabled: boolean;
  year_end_tax_reminder_enabled: boolean;
  goal_achievement_alerts_enabled: boolean;
  monthly_report_enabled: boolean;
  recommendation_drift_alert_enabled: boolean;
  challenge_reminders_enabled: boolean;
  goal_candidate_tickers: GoalCandidateTicker[];
  goal_risk_tolerance: GoalRiskTolerance;
  goal_max_weight_pct: number;
  goal_cagr_lookback_years: number;
  goal_short_term_equity_floor_pct: number;
  goal_bond_ceiling_pct: number | null;
  goal_cash_ceiling_pct: number | null;
  age_group: AgeGroup | null;
  birth_year: number | null;
  income_bracket: IncomeBracket | null;
  auto_rebalancing_max_order_value_krw: number;
  auto_rebalancing_daily_value_cap_krw: number | null;
}

export const fetchSettings = (): Promise<SettingsData> => apiGet<SettingsData>("/settings");

export const registerPushToken = (fcm_token: string | null) =>
  apiPut("/settings/push-token", { fcm_token });

export const updateCompositeSignalAlerts = (enabled: boolean) =>
  apiPut("/settings/composite-signal-alerts", { enabled });

export const updateMarketSignalDigest = (enabled: boolean) =>
  apiPut("/settings/market-signal-digest", { enabled });

/** AUTO 리밸런싱 하루 합산 거래대금 상한(KRW). null이면 무제한. */
export const updateAutoRebalancingDailyCap = (daily_value_cap_krw: number | null) =>
  apiPut("/settings/auto-rebalancing-daily-cap", { daily_value_cap_krw });

export const updateIncomeBracket = (income_bracket: IncomeBracket | null) =>
  apiPut("/settings/income-bracket", { income_bracket });

export const updateYearEndTaxReminder = (enabled: boolean) =>
  apiPut("/settings/year-end-tax-reminder", { enabled });

export const updateGoalAchievementAlerts = (enabled: boolean) =>
  apiPut("/settings/goal-achievement-alerts", { enabled });

export const updateMonthlyReportAlerts = (enabled: boolean) =>
  apiPut("/settings/monthly-report-alerts", { enabled });

export const updateRecommendationDriftAlert = (enabled: boolean) =>
  apiPut("/settings/recommendation-drift-alert", { enabled });

export const updateChallengeReminders = (enabled: boolean) =>
  apiPut("/settings/challenge-reminders", { enabled });

export const updateGoalCandidateTickers = (tickers: GoalCandidateTicker[]) =>
  apiPut("/settings/goal-candidate-tickers", { tickers });

export const updateGoalRecommendationOptions = (payload: GoalRecommendationOptions) =>
  apiPut("/settings/goal-recommendation-options", payload);
