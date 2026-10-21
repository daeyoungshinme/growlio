import { apiDelete, apiGet, apiPost, apiPut } from "./client";
import type { MarketRiskLevel } from "./marketSignals";

/** QQQ/SPY 전술 배분 국면 — 백엔드 tactical_allocation_service.Regime */
export type TacticalRegime = "RISK_ON" | "NEUTRAL" | "RISK_OFF";
export type TrendState = "UP" | "NEUTRAL" | "DOWN" | "UNKNOWN";
/** DIA(다우)는 비중표에만 쓰이고 국면 판정에는 쓰이지 않는다 */
export type TacticalAsset = "QQQ" | "SPY" | "DIA" | "CASH";
export type TacticalWeights = Record<TacticalAsset, number>;
export type RegimeWeightsTable = Record<TacticalRegime, TacticalWeights>;
/** 나스닥/S&P 틸트 — 백엔드 tactical_tilt.Tilt (주식 몫 안에서 QQQ↔SPY 이동) */
export type TacticalTilt = "FAVOR_QQQ" | "BALANCED" | "FAVOR_SPY";

export interface TiltInputs {
  real_yield: number | null; // 미국 10년 실질금리(%)
  real_yield_change_pp: number | null; // 20거래일 변화(%p)
  relative_strength_pct: number | null; // QQQ/SPY 비율의 50일 평균 대비(%)
}

export interface TechnicalSnapshot {
  close: number | null;
  sma50: number | null;
  sma200: number | null;
  rsi14: number | null;
  macd_hist: number | null;
  drawdown_pct: number | null; // 52주 고점 대비(%, 0 이하)
  trend: TrendState;
}

export interface TacticalStatus {
  portfolio_id: string;
  portfolio_name: string;
  enabled: boolean;
  notify_enabled: boolean;
  macro_level: MarketRiskLevel;
  macro_freshness: "LIVE" | "CACHED" | "PARTIAL" | "STALE";
  technicals: Partial<Record<"QQQ" | "SPY" | "DIA", TechnicalSnapshot>>;
  observed_regime: TacticalRegime | null; // 오늘 관측(판정 불가면 null)
  confirmed_regime: TacticalRegime | null; // 2일 확정 국면(전략 켠 경우)
  pending_regime: TacticalRegime | null;
  regime_changed_at: string | null;
  applied_regime: TacticalRegime | null;
  reasons: string[];
  regime_weights: RegimeWeightsTable;
  is_default_weights: boolean;
  proposed_weights: TacticalWeights | null;
  current_weights: Record<string, number>;
  /** 포트폴리오가 QQQ/SPY/DIA/CASH로만 구성됐는지 — false면 적용 시 다른 종목이 목표에서 빠진다 */
  portfolio_compatible: boolean;
  /** 틸트 이동폭(%p, 0이면 끔). proposed_weights에는 이미 반영돼 있다 */
  tilt_shift_pct: number;
  observed_tilt: TacticalTilt; // 오늘 판정
  confirmed_tilt: TacticalTilt; // 제안 비중에 쓰는 값(전략 켠 경우 월 1회 갱신값)
  tilt_evaluated_on: string | null;
  tilt_inputs: TiltInputs | null;
  tilt_reasons: string[];
}

export interface TacticalStrategyPayload {
  notify_enabled: boolean;
  regime_weights?: RegimeWeightsTable | null;
  /** 생략하면 서버 기본값(10)으로 저장되므로 설정 변경 시에는 현재 값을 함께 보낸다 */
  tilt_shift_pct?: number;
}

export interface TacticalBacktestMetric {
  name: string;
  total_return_pct: number;
  cagr_pct: number;
  mdd_pct: number;
  sharpe_ratio: number;
  volatility_pct: number;
  sortino_ratio: number;
}

export interface TacticalBacktestResult {
  years: number;
  start_date: string;
  end_date: string;
  metrics: TacticalBacktestMetric[]; // [전술 배분, SPY 보유, QQQ 보유, (DIA 시세가 있으면) DIA 보유]
  series: { date: string; strategy: number; spy: number; qqq: number; dia?: number }[];
  regime_switches: number;
  regime_time_pct: Record<TacticalRegime, number>;
  tilt_shift_pct: number;
  tilt_switches: number;
  tilt_time_pct: Record<TacticalTilt, number>;
  regime_timeline: { date: string; regime: TacticalRegime }[];
  macro_note: string;
  assumptions: string;
}

export const fetchTacticalStatus = (portfolioId: string) =>
  apiGet<TacticalStatus>(`/tactical/${portfolioId}`);

export const upsertTacticalStrategy = (portfolioId: string, payload: TacticalStrategyPayload) =>
  apiPut<TacticalStatus>(`/tactical/${portfolioId}`, payload);

export const deleteTacticalStrategy = (portfolioId: string) =>
  apiDelete(`/tactical/${portfolioId}`);

export const applyTacticalWeights = (portfolioId: string) =>
  apiPost<TacticalStatus>(`/tactical/${portfolioId}/apply`);

export const fetchTacticalBacktest = (portfolioId: string, years: number) =>
  apiGet<TacticalBacktestResult>(`/tactical/${portfolioId}/backtest`, { params: { years } });
