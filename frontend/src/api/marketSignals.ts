import { apiGet } from "./client";

export type MarketRiskLevel = "GREEN" | "YELLOW" | "RED";
export type VixLevel = "LOW" | "MEDIUM" | "MEDIUM_HIGH" | "HIGH";
export type YieldCurveState = "POSITIVE" | "FLAT" | "INVERTED" | "DEEPLY_INVERTED";
export type RateCutExpectationLevel =
  | "NEUTRAL"
  | "MILD_CUT_EXPECTED"
  | "CUT_EXPECTED"
  | "DEEP_CUT_EXPECTED";

export interface VixSignal {
  value: number;
  level: VixLevel;
  date: string;
  sub_score: number;
}

/** 장단기금리차(T10Y2Y)+금리인하기대(DGS2-FEDFUNDS) 병합 신호 — 둘 다 "Fed 정책금리 경로 기대"를
 * 반영해 이중계상 방지 목적으로 병합됨(sub_score는 두 원신호 중 worst-case). */
export interface UsRateCurveSignal {
  yield_curve_value: number | null;
  yield_curve_state: YieldCurveState | null;
  rate_cut_value: number | null; // DGS2 - FEDFUNDS 스프레드(%p)
  rate_cut_level: RateCutExpectationLevel | null;
  date: string;
  sub_score: number;
}

export type HighYieldSpreadLevel = "NORMAL" | "ELEVATED" | "STRESSED" | "CRISIS";
export type DollarIndexLevel = "NORMAL" | "ELEVATED" | "HIGH" | "BREAKOUT";
export type ExchangeRateLevel = "NORMAL" | "ELEVATED" | "HIGH" | "BREAKOUT";
export type OilPriceLevel = "NORMAL" | "ELEVATED" | "HIGH" | "BREAKOUT";

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

export interface ExchangeRateSignal {
  value: number; // 원/달러 환율(DEXKOUS)
  ma20: number;
  deviation_pct: number;
  level: ExchangeRateLevel;
  date: string;
  sub_score: number;
}

export interface OilPriceSignal {
  value: number; // WTI 현물유가(DCOILWTICO)
  ma20: number;
  deviation_pct: number; // 급등/급락 모두 절대값 기준으로 레벨 판정
  level: OilPriceLevel;
  date: string;
  sub_score: number;
}

export type InflationLevel = "NORMAL" | "ELEVATED" | "HIGH" | "BREAKOUT";
export type EmploymentLevel = "NORMAL" | "WATCH" | "SAHM_TRIGGERED" | "HIGH";

/** CPI(CPIAUCSL)+PCE(PCEPI) YoY 병합 신호 — 둘 다 "미국 인플레이션 추세"를 반영해
 * 이중계상 방지 목적으로 병합됨(sub_score는 두 원신호 중 worst-case). */
export interface InflationSignal {
  cpi_yoy_pct: number | null;
  cpi_level: InflationLevel | null;
  pce_yoy_pct: number | null;
  pce_level: InflationLevel | null;
  date: string;
  sub_score: number;
}

/** FRED UNRATE(미국 실업률) 기반 Sahm Rule의 단순화 버전 —
 * 최근 12개월 최저치 대비 상승폭(rise_from_low_pp)으로 경기침체 신호를 판단. */
export interface EmploymentSignal {
  value: number; // 실업률(%)
  trailing_12mo_low: number;
  rise_from_low_pp: number;
  level: EmploymentLevel;
  date: string;
  sub_score: number;
}

export interface MarketSignalResponse {
  composite_level: MarketRiskLevel;
  composite_score: number;
  composite_score_max: number;
  signals: {
    vix: VixSignal | null;
    us_rate_curve: UsRateCurveSignal | null;
    high_yield_spread: HighYieldSpreadSignal | null;
    dollar_index: DollarIndexSignal | null;
    exchange_rate: ExchangeRateSignal | null;
    oil_price: OilPriceSignal | null;
    inflation: InflationSignal | null;
    employment: EmploymentSignal | null;
  };
  computed_at: string;
  data_freshness: "LIVE" | "CACHED" | "PARTIAL" | "STALE";
}

export const fetchMarketSignal = () => apiGet<MarketSignalResponse>("/market-signals");
