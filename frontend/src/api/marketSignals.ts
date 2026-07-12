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

export type HighYieldSpreadLevel = "NORMAL" | "ELEVATED" | "STRESSED" | "CRISIS";
export type DollarIndexLevel = "NORMAL" | "ELEVATED" | "HIGH" | "BREAKOUT";
export type RateCutExpectationLevel =
  | "NEUTRAL"
  | "MILD_CUT_EXPECTED"
  | "CUT_EXPECTED"
  | "DEEP_CUT_EXPECTED";
export type ExchangeRateLevel = "NORMAL" | "ELEVATED" | "HIGH" | "BREAKOUT";

export interface HighYieldSpreadSignal {
  value: number;
  level: HighYieldSpreadLevel;
  date: string;
  sub_score: number;
}

export interface DollarIndexSignal {
  value: number;
  ma20: number;
  deviation_pct: number;
  level: DollarIndexLevel;
  date: string;
  sub_score: number;
}

export interface RateCutExpectationSignal {
  value: number; // DGS2 - FEDFUNDS 스프레드(%p)
  dgs2: number;
  fedfunds: number;
  level: RateCutExpectationLevel;
  date: string;
  sub_score: number;
}

export interface ExchangeRateSignal {
  value: number; // 원/달러 환율(DEXKOUS)
  ma20: number;
  deviation_pct: number;
  level: ExchangeRateLevel;
  date: string;
  sub_score: number;
}

export interface MarketSignalResponse {
  composite_level: MarketRiskLevel;
  composite_score: number;
  composite_score_max: number;
  fear_greed_contrarian_buy: boolean;
  fear_greed_extreme_greed: boolean;
  signals: {
    vix: VixSignal | null;
    yield_curve: YieldCurveSignal | null;
    fear_greed: FearGreedSignal | null;
    high_yield_spread: HighYieldSpreadSignal | null;
    dollar_index: DollarIndexSignal | null;
    rate_cut_expectation: RateCutExpectationSignal | null;
    exchange_rate: ExchangeRateSignal | null;
  };
  computed_at: string;
  data_freshness: "LIVE" | "CACHED" | "PARTIAL" | "STALE";
}

export const fetchMarketSignal = () => apiGet<MarketSignalResponse>("/market-signals");
