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

export interface GoalRecommendationOptions {
  risk_tolerance: GoalRiskTolerance;
  max_weight_pct: number;
  cagr_lookback_years: number;
  short_term_equity_floor_pct: number;
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
  goal_achievement_alerts_enabled: boolean;
  monthly_report_enabled: boolean;
  goal_candidate_tickers: GoalCandidateTicker[];
  goal_risk_tolerance: GoalRiskTolerance;
  goal_max_weight_pct: number;
  goal_cagr_lookback_years: number;
  goal_short_term_equity_floor_pct: number;
  auto_rebalancing_max_order_value_krw: number;
}

export const fetchSettings = (): Promise<SettingsData> => apiGet<SettingsData>("/settings");

export const registerPushToken = (fcm_token: string | null) =>
  apiPut("/settings/push-token", { fcm_token });

export const updateCompositeSignalAlerts = (enabled: boolean) =>
  apiPut("/settings/composite-signal-alerts", { enabled });

export const updateMarketSignalDigest = (enabled: boolean) =>
  apiPut("/settings/market-signal-digest", { enabled });

export const updateGoalAchievementAlerts = (enabled: boolean) =>
  apiPut("/settings/goal-achievement-alerts", { enabled });

export const updateMonthlyReportAlerts = (enabled: boolean) =>
  apiPut("/settings/monthly-report-alerts", { enabled });

export const updateGoalCandidateTickers = (tickers: GoalCandidateTicker[]) =>
  apiPut("/settings/goal-candidate-tickers", { tickers });

export const updateGoalRecommendationOptions = (payload: GoalRecommendationOptions) =>
  apiPut("/settings/goal-recommendation-options", payload);
