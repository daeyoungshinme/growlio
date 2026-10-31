import type { DividendYield } from "@/types";
import type { groupPositionsByTicker } from "@/utils/portfolio";
import { DOMESTIC_MARKETS } from "@/constants/markets";
import { fmtUsd } from "@/utils/format";

export type AggSortKey = "total_value_krw" | "pnl_pct" | "total_pnl" | "weight_in_stock";
type SortDir = "asc" | "desc";
export interface SortState {
  key: AggSortKey;
  dir: SortDir;
}

export type Agg = ReturnType<typeof groupPositionsByTicker>[number];

/** 종목 행·카드·배당맵이 공유하는 키 */
export function holdingKey(agg: Agg): string {
  return `${agg.ticker}-${agg.market}`;
}

/** 보유수량 기준 예상 연배당 — 국내는 원, 해외는 달러 단위(dps 원통화) 그대로 표시. */
export function annualDividendLabel(divData: DividendYield, qty: number): string | null {
  if (divData.dps <= 0) return null;
  const total = divData.dps * qty;
  return DOMESTIC_MARKETS.includes(divData.market.toUpperCase())
    ? `${Math.round(total).toLocaleString()}원`
    : fmtUsd(total);
}
