import { apiGet, apiPut } from "./client";

export interface SettingsData {
  has_kis: boolean;
  has_dart: boolean;
  has_open_banking: boolean;
  ob_token_expires_at: string | null;
  goal_amount: number | null;
  goal_annual_return_pct: number | null;
  annual_deposit_goal: number | null;
  monthly_deposit_amount: number | null;
  retirement_target_year: number | null;
  user_email: string;
  notification_email: string | null;
  auto_dca_enabled: boolean;
  auto_dca_day: number | null;
  auto_dca_amount: number | null;
  auto_dca_portfolio_id: string | null;
  auto_dca_account_id: string | null;
  auto_dca_last_executed_at: string | null;
  annual_dividend_goal: number | null;
  fcm_token_stored: boolean;
}

export interface AutoDcaPayload {
  enabled: boolean;
  day: number | null;
  amount: number | null;
  portfolio_id: string | null;
  account_id: string | null;
}

export const fetchSettings = (): Promise<SettingsData> => apiGet<SettingsData>("/settings");

export const updateAutoDca = (payload: AutoDcaPayload) => apiPut("/settings/auto-dca", payload);

export const registerPushToken = (fcm_token: string | null) =>
  apiPut("/settings/push-token", { fcm_token });
