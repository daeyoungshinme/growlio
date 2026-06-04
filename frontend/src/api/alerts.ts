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
  mode: "NOTIFY" | "AUTO";
  strategy: "FULL" | "BUY_ONLY";
  account_id: string | null;
  order_type: "MARKET" | "LIMIT";
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
  mode: "NOTIFY" | "AUTO";
  strategy: "FULL" | "BUY_ONLY";
  account_id: string | null;
  order_type: "MARKET" | "LIMIT";
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

// ── 주가 목표 알림 ──────────────────────────────────────────────────────────

export interface StockPriceAlert {
  id: string;
  ticker: string;
  market: string;
  name: string;
  target_price: number;
  direction: "BELOW" | "ABOVE";
  is_active: boolean;
  max_trigger_count: number;
  trigger_count: number;
  triggered_at: string | null;
  created_at: string;
}

export const fetchStockPriceAlerts = () =>
  api.get<StockPriceAlert[]>("/alerts/stock-price").then((r) => r.data);

export const createStockPriceAlert = (body: {
  ticker: string;
  market: string;
  name: string;
  target_price: number;
  direction: "BELOW" | "ABOVE";
  max_trigger_count?: number;
}) => api.post<StockPriceAlert>("/alerts/stock-price", body).then((r) => r.data);

export const reactivateStockPriceAlert = (id: string) =>
  api.patch<StockPriceAlert>(`/alerts/stock-price/${id}/reactivate`).then((r) => r.data);

export const deleteStockPriceAlert = (id: string) =>
  api.delete(`/alerts/stock-price/${id}`).then((r) => r.data);

export interface AlertHistoryItem {
  id: string;
  alert_type: "EXCHANGE_RATE" | "REBALANCING" | "STOCK_PRICE";
  message: string;
  created_at: string;
}

export const fetchAlertHistory = (params?: { skip?: number; limit?: number }) =>
  api.get<AlertHistoryItem[]>("/alerts/history", { params }).then((r) => r.data);
