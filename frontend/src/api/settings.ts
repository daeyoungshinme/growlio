import { api } from "./client";

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
}

export const fetchSettings = (): Promise<SettingsData> =>
  api.get<SettingsData>("/settings").then((r) => r.data);
