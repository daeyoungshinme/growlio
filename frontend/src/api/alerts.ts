import { api } from "./client";

export interface ExchangeRateAlert {
  id: string;
  target_rate: number;
  direction: "BELOW" | "ABOVE";
  is_active: boolean;
  max_trigger_count: number;
  trigger_count: number;
  triggered_at: string | null;
  created_at: string;
}

export const fetchExchangeRateAlerts = () =>
  api.get<ExchangeRateAlert[]>("/alerts/exchange-rate").then((r) => r.data);

export const createExchangeRateAlert = (
  target_rate: number,
  direction: "BELOW" | "ABOVE",
  max_trigger_count: number = 1,
) =>
  api
    .post<ExchangeRateAlert>("/alerts/exchange-rate", { target_rate, direction, max_trigger_count })
    .then((r) => r.data);

export const reactivateExchangeRateAlert = (id: string) =>
  api.patch<ExchangeRateAlert>(`/alerts/exchange-rate/${id}/reactivate`).then((r) => r.data);

export const deleteExchangeRateAlert = (id: string) =>
  api.delete(`/alerts/exchange-rate/${id}`).then((r) => r.data);

// ── 리밸런싱 알림 ──────────────────────────────────────────────────────────

export type ScheduleType = "DAILY" | "WEEKLY" | "MONTHLY" | "QUARTERLY" | "SEMIANNUAL" | "ANNUAL";

export interface RebalancingAlert {
  id: string;
  portfolio_id: string;
  is_active: boolean;
  threshold_pct: number;
  schedule_type: ScheduleType;
  schedule_day_of_week: number | null;
  schedule_day_of_month: number | null;
  only_when_drift: boolean;
  last_triggered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface RebalancingAlertUpsert {
  portfolio_id: string;
  threshold_pct: number;
  schedule_type: ScheduleType;
  schedule_day_of_week: number | null;
  schedule_day_of_month: number | null;
  only_when_drift: boolean;
}

export const fetchRebalancingAlerts = () =>
  api.get<RebalancingAlert[]>("/alerts/rebalancing").then((r) => r.data);

export const fetchRebalancingAlert = (portfolioId: string) =>
  api.get<RebalancingAlert>(`/alerts/rebalancing/${portfolioId}`).then((r) => r.data);

export const upsertRebalancingAlert = (
  portfolioId: string,
  body: Omit<RebalancingAlertUpsert, "portfolio_id">,
) =>
  api
    .put<RebalancingAlert>(`/alerts/rebalancing/${portfolioId}`, {
      portfolio_id: portfolioId,
      ...body,
    })
    .then((r) => r.data);

export const deleteRebalancingAlert = (portfolioId: string) =>
  api.delete(`/alerts/rebalancing/${portfolioId}`);
