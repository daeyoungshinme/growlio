import { api } from "./client";

export type InsightSeverity = "INFO" | "WARNING" | "ALERT";

export type InsightType =
  | "CONCENTRATION"
  | "UNDERPERFORMANCE"
  | "DEPOSIT_SHORTFALL"
  | "REBALANCING_OPPORTUNITY"
  | "TAX_LOSS_HARVEST"
  | "HIGH_COST";

export interface Insight {
  type: InsightType;
  severity: InsightSeverity;
  title: string;
  detail: string;
  action_label: string | null;
  action_url: string | null;
  metric_value: number | null;
}

export interface InsightsSummary {
  INFO: number;
  WARNING: number;
  ALERT: number;
}

export const fetchInsights = () =>
  api.get<Insight[]>("/insights").then((r) => r.data);

export const fetchInsightsSummary = () =>
  api.get<InsightsSummary>("/insights/summary").then((r) => r.data);
