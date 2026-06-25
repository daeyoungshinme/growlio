import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";

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

export const fetchExchangeRateAlerts = () => apiGet<ExchangeRateAlert[]>("/alerts/exchange-rate");

export const createExchangeRateAlert = (
  target_rate: number,
  direction: "BELOW" | "ABOVE",
  max_trigger_count: number = 1,
) =>
  apiPost<ExchangeRateAlert>("/alerts/exchange-rate", {
    target_rate,
    direction,
    max_trigger_count,
  });

export const reactivateExchangeRateAlert = (id: string) =>
  apiPatch<ExchangeRateAlert>(`/alerts/exchange-rate/${id}/reactivate`);

export const deleteExchangeRateAlert = (id: string) => apiDelete(`/alerts/exchange-rate/${id}`);

// ── 리밸런싱 알림 ──────────────────────────────────────────────────────────

export type ScheduleType = "DAILY" | "WEEKLY" | "MONTHLY" | "QUARTERLY" | "SEMIANNUAL" | "ANNUAL";
export type MarketConditionMode = "DISABLED" | "CAUTIOUS" | "STRICT";
export type TriggerCondition = "DRIFT_ONLY" | "SCHEDULE_ONLY" | "BOTH";

export interface RebalancingAlert {
  id: string;
  portfolio_id: string;
  is_active: boolean;
  threshold_pct: number;
  schedule_type: ScheduleType;
  schedule_day_of_week: number | null;
  schedule_day_of_month: number | null;
  trigger_condition: TriggerCondition;
  mode: "NOTIFY" | "AUTO";
  strategy: "FULL" | "BUY_ONLY" | "TWO_PHASE";
  account_id: string | null;
  order_type: "MARKET" | "LIMIT";
  market_condition_mode: MarketConditionMode;
  auto_execution_time: string | null;
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
  trigger_condition: TriggerCondition;
  mode: "NOTIFY" | "AUTO";
  strategy: "FULL" | "BUY_ONLY" | "TWO_PHASE";
  account_id: string | null;
  order_type: "MARKET" | "LIMIT";
  market_condition_mode: MarketConditionMode;
  auto_execution_time: string | null;
}

export const fetchRebalancingAlerts = () => apiGet<RebalancingAlert[]>("/alerts/rebalancing");

export const fetchRebalancingAlert = (portfolioId: string) =>
  apiGet<RebalancingAlert>(`/alerts/rebalancing/${portfolioId}`);

export const upsertRebalancingAlert = (
  portfolioId: string,
  body: Omit<RebalancingAlertUpsert, "portfolio_id">,
) =>
  apiPut<RebalancingAlert>(`/alerts/rebalancing/${portfolioId}`, {
    portfolio_id: portfolioId,
    ...body,
  });

export const deleteRebalancingAlert = (portfolioId: string) =>
  apiDelete(`/alerts/rebalancing/${portfolioId}`);

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

export const fetchStockPriceAlerts = () => apiGet<StockPriceAlert[]>("/alerts/stock-price");

export const createStockPriceAlert = (body: {
  ticker: string;
  market: string;
  name: string;
  target_price: number;
  direction: "BELOW" | "ABOVE";
  max_trigger_count?: number;
}) => apiPost<StockPriceAlert>("/alerts/stock-price", body);

export const reactivateStockPriceAlert = (id: string) =>
  apiPatch<StockPriceAlert>(`/alerts/stock-price/${id}/reactivate`);

export const deleteStockPriceAlert = (id: string) => apiDelete(`/alerts/stock-price/${id}`);

export interface AlertHistoryItem {
  id: string;
  alert_type: "EXCHANGE_RATE" | "REBALANCING" | "STOCK_PRICE";
  message: string;
  created_at: string;
}

export const fetchAlertHistory = (params?: { skip?: number; limit?: number }) =>
  apiGet<AlertHistoryItem[]>("/alerts/history", { params });
