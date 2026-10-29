import { apiGet } from "./client";

export type InsightSeverity = "INFO" | "WARNING" | "ALERT";

// 백엔드 insight_service.InsightType과 같은 집합
export type InsightType = "CONCENTRATION" | "REBALANCING_OPPORTUNITY" | "TAX_LOSS_HARVEST";

export interface Insight {
  type: InsightType;
  severity: InsightSeverity;
  title: string;
  detail: string;
  action_label: string | null;
  action_url: string | null;
  metric_value: number | null;
}

export const fetchInsights = () => apiGet<Insight[]>("/insights");
