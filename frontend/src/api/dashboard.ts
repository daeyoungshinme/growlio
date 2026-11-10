import { apiGet } from "./client";
import type { ActionPriority } from "@/utils/actionPriority";

export interface DashboardAllocationItem {
  type: string;
  amount_krw: number;
  pct: number;
}

export interface DashboardData {
  total_assets_krw: number;
  /** 부동산 제외 — 목표 진행률의 분자. 옛 persist 캐시에는 없을 수 있다 */
  investable_assets_krw?: number | null;
  asset_allocation: DashboardAllocationItem[];
  goal_amount: number | null;
  goal_achievement_pct: number | null;
  stock_return_pct: number;
  annual_return_pct: number | null;
  annual_deposit_goal: number | null;
  annual_deposit_current: number;
  deposit_achievement_pct: number | null;
  estimated_annual_dividends: number | null;
  cumulative_return_pct: number | null;
  xirr_pct: number | null;
  goal_annual_return_pct: number | null;
  return_goal_gap_pct: number | null;
  retirement_target_year: number | null;
  annual_dividend_goal: number | null;
  dividend_goal_achievement_pct: number | null;
}

export const fetchDashboard = () => apiGet<DashboardData>("/dashboard");

export type ActionItemKind =
  | "TACTICAL"
  | "REBALANCE"
  | "DCA_SHORTFALL"
  | "DCA_FX_WAITING"
  | "FX_PLAN"
  | "TAX_WARNING"
  | "TAX_ACTION"
  | "CHALLENGE"
  | "PARTIAL_FAILURE";

/** 홈 "지금 할 일" 1행 — 백엔드 `action_items_service`가 우선순위·마감 순으로 최대 5건 반환 */
export interface ActionItem {
  id: string;
  kind: ActionItemKind;
  priority: ActionPriority;
  title: string;
  detail: string;
  cta_label: string;
  link: string;
  deadline: string | null;
}

/** 이탈 포트폴리오 2개 이상을 묶은 REBALANCE 행의 id — 백엔드 `action_items_service.REBALANCE_GROUP_ID`와 같은 값.
 * 이 행은 링크 대신 drift-summary로 포트폴리오 목록을 펼친다(docs/plans/73). */
export const REBALANCE_GROUP_ID = "rebalance:all";

export const fetchActionItems = () => apiGet<ActionItem[]>("/dashboard/action-items");
