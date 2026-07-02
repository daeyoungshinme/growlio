import { apiGet } from "./client";

export type MarketRiskLevel = "GREEN" | "YELLOW" | "RED";
export type VixLevel = "LOW" | "MEDIUM" | "MEDIUM_HIGH" | "HIGH";
export type YieldCurveState = "POSITIVE" | "FLAT" | "INVERTED" | "DEEPLY_INVERTED";
export type FearGreedClassification =
  | "EXTREME_FEAR"
  | "FEAR"
  | "NEUTRAL"
  | "GREED"
  | "EXTREME_GREED";

export interface VixSignal {
  value: number;
  level: VixLevel;
  date: string;
  sub_score: number;
}

export interface YieldCurveSignal {
  value: number;
  state: YieldCurveState;
  date: string;
  sub_score: number;
}

export interface FearGreedSignal {
  value: number;
  classification: FearGreedClassification;
  label: string;
  label_en: string;
  sub_score: number;
}

export interface MarketSignalResponse {
  composite_level: MarketRiskLevel;
  composite_score: number;
  fear_greed_contrarian_buy: boolean;
  fear_greed_extreme_greed: boolean;
  signals: {
    vix: VixSignal | null;
    yield_curve: YieldCurveSignal | null;
    fear_greed: FearGreedSignal | null;
  };
  computed_at: string;
  data_freshness: "LIVE" | "CACHED" | "PARTIAL" | "STALE";
}

export const fetchMarketSignal = () => apiGet<MarketSignalResponse>("/market-signals");
