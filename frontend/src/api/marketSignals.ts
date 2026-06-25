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

// ---------------------------------------------------------------------------
// 거시경제 진단
// ---------------------------------------------------------------------------

export type CpiDirection = "rising" | "flat" | "falling";
export type FedRateDirection = "rising" | "stable" | "falling";
export type GrowthBias = "bullish" | "neutral" | "bearish";

export interface CpiTrend {
  direction: CpiDirection;
  latest_value: number;
  latest_date: string;
  yoy_pct: number | null;
  change_3m: number | null;
  month_count: number;
}

export interface FedRateInfo {
  latest_value: number;
  latest_date: string;
  direction: FedRateDirection;
  is_high: boolean;
}

export interface FomcInfo {
  next_meeting_date: string | null;
  days_until: number | null;
  source: "calendar" | "fallback" | "unknown";
}

export interface MacroImplication {
  label: string;
  growth_bias: GrowthBias;
  message: string;
  action: string;
}

export interface MacroDiagnosisResponse {
  cpi: CpiTrend | null;
  fed_rate: FedRateInfo | null;
  fomc: FomcInfo;
  implication: MacroImplication | null;
  data_freshness: "LIVE" | "PARTIAL" | "STALE";
  computed_at: string;
}

export const fetchMacroDiagnosis = () =>
  apiGet<MacroDiagnosisResponse>("/market-signals/macro-diagnosis");
