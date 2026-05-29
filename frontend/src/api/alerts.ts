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
