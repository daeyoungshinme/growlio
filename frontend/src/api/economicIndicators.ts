import { apiGet } from "./client";

export interface InflationIndicatorSummary {
  code: "CPI_US" | "CORE_CPI_US";
  name: string;
  latest_value: number;
  latest_date: string;
  mom_change_pct: number | null;
  yoy_change_pct: number | null;
  next_release_date: string | null;
}

export const fetchInflationSummary = () =>
  apiGet<InflationIndicatorSummary[]>("/economic-indicators/inflation-summary");
