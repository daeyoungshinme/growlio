import { api } from "./client";

export interface ExchangeRateAlert {
  id: string;
  target_rate: number;
  direction: "BELOW" | "ABOVE";
  is_active: boolean;
  triggered_at: string | null;
  created_at: string;
}

export const fetchExchangeRateAlerts = () =>
  api.get<ExchangeRateAlert[]>("/alerts/exchange-rate").then((r) => r.data);

export const createExchangeRateAlert = (target_rate: number, direction: "BELOW" | "ABOVE") =>
  api.post<ExchangeRateAlert>("/alerts/exchange-rate", { target_rate, direction }).then((r) => r.data);

export const deleteExchangeRateAlert = (id: string) =>
  api.delete(`/alerts/exchange-rate/${id}`).then((r) => r.data);
