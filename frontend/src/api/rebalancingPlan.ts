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
  "PENDING" | "WAITING_FX" | "EXECUTED" | "CANCELED" | "REJECTED" | "EXPIRED" | "FAILED";

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
  /** 이 leg는 실행되지 않고 끝났는데 같은 플랜의 다른 leg는 체결된 "반쪽 실행" 상태 */
  partially_executed: boolean;
  /** 환전 대기(WAITING_FX, plans/120) — 마지막 판정의 필요/보유 달러와 자동 재확인 기한 */
  required_usd?: number | null;
  available_usd?: number | null;
  fx_retry_until?: string | null;
  items: RebalancingPlanItemOut[];
}

export interface PlanActionResponse {
  status: string;
  message: string;
  required_usd?: number | null;
  available_usd?: number | null;
}

export interface PlanTokenPreview {
  valid: boolean;
  reason: "NOT_FOUND" | "ALREADY_DECIDED" | "EXPIRED" | "IN_PROGRESS" | "WAITING_FX" | null;
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

/** 환전 대기 적립 해외 매수 '다시 매수' — status: EXECUTED | SCHEDULED | STILL_SHORT | FAILED */
export const retryFxPlanLeg = (planId: string, legId: string) =>
  apiPost<PlanActionResponse>(`/rebalancing/plans/${planId}/legs/${legId}/retry-fx`);

// ── 인증 없음 (이메일 링크 전용) ─────────────────────────────────────────

export const fetchPlanPreview = (token: string) =>
  apiGet<PlanTokenPreview>(`/rebalancing/plan-actions/${token}`);

export const cancelBuyPlanByToken = (token: string) =>
  apiPost<PlanActionResponse>(`/rebalancing/plan-actions/${token}/buy/cancel`);

export const decideSellPlanByToken = (token: string, decision: "APPROVE" | "REJECT") =>
  apiPost<PlanActionResponse>(`/rebalancing/plan-actions/${token}/sell/decision`, { decision });
