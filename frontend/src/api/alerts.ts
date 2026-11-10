import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";
import { getHttpStatus } from "@/utils/error";

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
/** TACTICAL: 같은 포트폴리오 전술 배분이 방어 국면이면 자동매수 보류(plans/71) */
export type MarketConditionMode = "DISABLED" | "CAUTIOUS" | "STRICT" | "TACTICAL";
export type TriggerCondition = "DRIFT_ONLY" | "SCHEDULE_ONLY" | "BOTH";
export type TaxImpactGateMode = "DISABLED" | "ENABLED";

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
  notify_time: string;
  buy_wait_minutes: number;
  tax_impact_gate_mode: TaxImpactGateMode;
  max_tax_impact_krw: number | null;
  /** 정기 적립 정액(원, plans/120) — 있으면 매회 이 금액만 목표 비중대로 나눠 매수. 없으면 예수금 전체로 비중 채우기 */
  dca_amount_krw?: number | null;
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
  notify_time: string;
  buy_wait_minutes: number;
  tax_impact_gate_mode: TaxImpactGateMode;
  max_tax_impact_krw: number | null;
  dca_amount_krw?: number | null;
}

export const fetchRebalancingAlerts = () => apiGet<RebalancingAlert[]>("/alerts/rebalancing");

export const fetchRebalancingAlert = (portfolioId: string): Promise<RebalancingAlert | null> =>
  apiGet<RebalancingAlert>(`/alerts/rebalancing/${portfolioId}`).catch((e) => {
    if (getHttpStatus(e) === 404) return null;
    throw e;
  });

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

export interface TestAlertResult {
  email_sent: boolean;
  push_sent: boolean;
  message: string;
}

export const sendTestRebalancingAlert = (portfolioId: string) =>
  apiPost<TestAlertResult>(`/alerts/rebalancing/${portfolioId}/test`, {});

export type AlertScope = "AGGREGATE" | "PER_ACCOUNT";

export const updateAlertScope = (portfolioId: string, alertScope: AlertScope) =>
  apiPut<void>(`/alerts/rebalancing/${portfolioId}/scope`, { alert_scope: alertScope });

// ── 계좌별 독립 리밸런싱 알림 (PER_ACCOUNT 스코프) ─────────────────────────

export const fetchAccountRebalancingAlerts = (portfolioId: string) =>
  apiGet<RebalancingAlert[]>(`/alerts/rebalancing/${portfolioId}/accounts`);

export const fetchAccountRebalancingAlert = (portfolioId: string, accountId: string) =>
  fetchAccountRebalancingAlerts(portfolioId).then(
    (alerts) => alerts.find((a) => a.account_id === accountId) ?? null,
  );

export const upsertAccountRebalancingAlert = (
  portfolioId: string,
  accountId: string,
  body: Omit<RebalancingAlertUpsert, "portfolio_id">,
) =>
  apiPut<RebalancingAlert>(`/alerts/rebalancing/${portfolioId}/accounts/${accountId}`, {
    portfolio_id: portfolioId,
    ...body,
  });

export const deleteAccountRebalancingAlert = (portfolioId: string, accountId: string) =>
  apiDelete(`/alerts/rebalancing/${portfolioId}/accounts/${accountId}`);

export const sendTestAccountRebalancingAlert = (portfolioId: string, accountId: string) =>
  apiPost<TestAlertResult>(`/alerts/rebalancing/${portfolioId}/accounts/${accountId}/test`, {});

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
  /** 해외 종목인데 목표가가 1,000원 미만 — 달러 숫자를 원화로 저장한 옛 알림이라 판정에서 빠진다(plans/119 A3) */
  needs_reentry: boolean;
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
  // 백엔드가 GOAL_*·MONTHLY_REPORT·CHALLENGE_* 등도 기록하므로 넓게 받는다 (NotificationSettingsPage의 라벨 맵이 매핑)
  alert_type: string;
  message: string;
  created_at: string;
}

export const fetchAlertHistory = (params?: { skip?: number; limit?: number }) =>
  apiGet<AlertHistoryItem[]>("/alerts/history", { params });
