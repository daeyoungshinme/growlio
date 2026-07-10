import { apiGet, apiPost } from "./client";

export interface RebalancingPlanItemOut {
  ticker: string | null;
  name: string | null;
  market: string | null;
  quantity: number;
  account_id: string | null;
  order_type: "MARKET" | "LIMIT";
  limit_price: number | null;
  reference_price: number | null;
}

export type RebalancingPlanLegStatus =
  | "PENDING"
  | "EXECUTED"
  | "CANCELED"
  | "REJECTED"
  | "EXPIRED"
  | "FAILED";

export interface RebalancingPlanLegSummary {
  plan_id: string;
  leg_id: string;
  portfolio_id: string | null;
  portfolio_name: string | null;
  account_id: string | null;
  account_name: string | null;
  side: "BUY" | "SELL";
  status: RebalancingPlanLegStatus;
  deadline_at: string;
  decided_at: string | null;
  execution_id: string | null;
  error_message: string | null;
  actionable: boolean;
  items: RebalancingPlanItemOut[];
}

export interface PlanActionResponse {
  status: string;
  message: string;
}

export interface PlanTokenPreview {
  valid: boolean;
  reason: "NOT_FOUND" | "ALREADY_DECIDED" | "EXPIRED" | null;
  actionable: boolean;
  leg: RebalancingPlanLegSummary | null;
}

// ── 인증 필요 (앱 내) ────────────────────────────────────────────────────

export const fetchRecentPlanLegs = (limit = 30) =>
  apiGet<RebalancingPlanLegSummary[]>("/rebalancing/plans", { params: { limit } });

export const cancelPlanLeg = (planId: string, legId: string) =>
  apiPost<PlanActionResponse>(`/rebalancing/plans/${planId}/legs/${legId}/cancel`);

export const approvePlanLeg = (planId: string, legId: string) =>
  apiPost<PlanActionResponse>(`/rebalancing/plans/${planId}/legs/${legId}/approve`);

// ── 인증 없음 (이메일 링크 전용) ─────────────────────────────────────────

export const fetchPlanPreview = (token: string) =>
  apiGet<PlanTokenPreview>(`/rebalancing/plan-actions/${token}`);

export const cancelBuyPlanByToken = (token: string) =>
  apiPost<PlanActionResponse>(`/rebalancing/plan-actions/${token}/buy/cancel`);

export const decideSellPlanByToken = (token: string, decision: "APPROVE" | "REJECT") =>
  apiPost<PlanActionResponse>(`/rebalancing/plan-actions/${token}/sell/decision`, { decision });
