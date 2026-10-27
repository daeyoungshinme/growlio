import { apiDelete, apiGet, apiPost, apiPut } from "./client";
import type { MarketRiskLevel } from "./marketSignals";

/** 나스닥100/S&P500 전술 배분 국면 — 백엔드 tactical_allocation_service.Regime */
export type TacticalRegime = "RISK_ON" | "NEUTRAL" | "RISK_OFF";
export type TrendState = "UP" | "NEUTRAL" | "DOWN" | "UNKNOWN";
/** DIA(다우)·QLD·SSO(2배 레버리지)는 비중표에만 쓰이고 국면 판정에는 쓰이지 않는다 */
export type TacticalAsset = "QQQ" | "SPY" | "DIA" | "QLD" | "SSO" | "CASH";
/** 백엔드 technical_indicators.PullbackStage — 종가가 가장 깊이 내려간 이평선(웅덩이매매법 분할매수 구간) */
export type PullbackStage = "NONE" | "SMA20" | "SMA60" | "SMA120" | "SMA120_RSI" | "UNKNOWN";
export type TacticalWeights = Record<TacticalAsset, number>;
export type RegimeWeightsTable = Record<TacticalRegime, TacticalWeights>;
/** 나스닥/S&P 틸트 — 백엔드 tactical_tilt.Tilt (주식 몫 안에서 QQQ↔SPY 이동) */
export type TacticalTilt = "FAVOR_QQQ" | "BALANCED" | "FAVOR_SPY";

export interface TiltInputs {
  real_yield: number | null; // 미국 10년 실질금리(%)
  real_yield_change_pp: number | null; // 20거래일 변화(%p)
  relative_strength_pct: number | null; // QQQ/SPY 비율의 50일 평균 대비(%)
}

/** 다음 국면 전환 후보까지 남은 조건 — 백엔드 tactical_hints.TransitionHint */
export interface TransitionHint {
  kind: "TO_RISK_OFF" | "TO_NEUTRAL" | "TO_RISK_ON";
  text: string;
  distance_pct: number | null; // 종가 기준 필요한 가격 변동(%), 가격 조건이 아니면 null
}

export interface TechnicalSnapshot {
  close: number | null;
  sma20?: number | null;
  sma60?: number | null;
  sma120?: number | null;
  sma50: number | null;
  sma200: number | null;
  rsi14: number | null;
  macd_hist: number | null;
  drawdown_pct: number | null; // 52주 고점 대비(%, 0 이하)
  trend: TrendState;
  pullback_stage?: PullbackStage;
}

/** 백엔드 tactical_allocation_service.current_groups 값 */
export interface TacticalGroupSummary {
  label: string;
  primary: string; // 대표 매수 종목
  member_count: number; // 대표 외 합산 종목 수(국내 대체 제외)
  domestic_alt: string | null;
}

export interface TacticalStatus {
  portfolio_id: string;
  portfolio_name: string;
  enabled: boolean;
  notify_enabled: boolean;
  /** false면 매크로를 무시하고 차트 추세만으로 국면 판정(전략별 옵션, plans/70) */
  use_macro: boolean;
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
  /** 현재 목표 비중 — 나스닥100·S&P500·다우 지수 그룹은 대표 종목과 무관하게 QQQ·SPY·DIA 키, 그 외 종목은 ticker 키 */
  current_weights: Record<string, number>;
  /** 전술 자산별 지수 그룹 구성(plans/76) — 그룹이 아닌 자산은 없음. 적용해도 대표·멤버·국내 대체는 유지된다 */
  current_groups: Partial<Record<TacticalAsset, TacticalGroupSummary>>;
  /** 포트폴리오가 전술 자산(나스닥100·S&P500·다우 그룹, QLD/SSO, 현금)으로만 구성됐는지 — false면 적용 시 다른 종목이 목표에서 빠진다 */
  portfolio_compatible: boolean;
  /** 틸트 이동폭(%p, 0이면 끔). proposed_weights에는 이미 반영돼 있다 */
  tilt_shift_pct: number;
  observed_tilt: TacticalTilt; // 오늘 판정
  confirmed_tilt: TacticalTilt; // 제안 비중에 쓰는 값(전략 켠 경우 월 1회 갱신값)
  tilt_evaluated_on: string | null;
  tilt_inputs: TiltInputs | null;
  tilt_reasons: string[];
  /** 웅덩이(눌림목) 현금 투입 최대폭(%p, 0이면 끔). 공격 국면에서만 proposed_weights에 반영된다 */
  dip_shift_pct: number;
  /** 현재 투입 단계 0~3(60일선/120일선/120일선+RSI 과매도) — 공격 국면이 아니면 0 */
  dip_level: number;
  /** 제안 비중에 실제로 들어간 투입량(%p) — 명목 투입량이 현금 비중을 넘으면 현금까지만 */
  dip_deployed_pct: number;
  /** QQQ 웅덩이 단계(오늘) */
  pullback_stage: PullbackStage;
  dip_reasons: string[];
  /** 확정 국면에서 절반만 먼저 적용했으면 그 국면(남은 절반 대기) — 아니면 null */
  partial_regime: TacticalRegime | null;
  partial_applied_on: string | null; // "YYYY-MM-DD"
  transition_hints: TransitionHint[];
}

export interface TacticalStrategyPayload {
  notify_enabled: boolean;
  regime_weights?: RegimeWeightsTable | null;
  /** 생략하면 서버 기본값(0 = 끔)으로 저장되므로 설정 변경 시에는 현재 값을 함께 보낸다 */
  tilt_shift_pct?: number;
  /** 생략하면 0(끔)으로 저장되므로 설정 변경 시에는 현재 값을 함께 보낸다 */
  dip_shift_pct?: number;
  /** 생략하면 true(매크로 반영)로 저장되므로 설정 변경 시에는 현재 값을 함께 보낸다 */
  use_macro?: boolean;
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
  /** [전술 배분, 평균 비중 고정, SPY 보유, QQQ 보유, (DIA 시세가 있으면) DIA 보유] */
  metrics: TacticalBacktestMetric[];
  series: {
    date: string;
    strategy: number;
    static: number;
    spy: number;
    qqq: number;
    dia?: number;
  }[];
  /** 전술 배분이 기간 중 평균적으로 든 목표 비중(시간가중) — "평균 비중 고정" 비교선의 비중 */
  avg_weights: TacticalWeights;
  turnover_pct_per_year: number; // 연평균 회전율(%)
  regime_switches: number;
  regime_time_pct: Record<TacticalRegime, number>;
  tilt_shift_pct: number;
  tilt_switches: number;
  tilt_time_pct: Record<TacticalTilt, number>;
  dip_shift_pct?: number;
  dip_entries?: number; // 웅덩이 진입 횟수
  dip_time_pct?: number; // 투입 상태였던 기간 비율(%)
  regime_timeline: { date: string; regime: TacticalRegime }[];
  macro_note: string;
  assumptions: string;
}

/** 전술 배분을 켠 포트폴리오 — 백엔드 GET /tactical(저장 상태만, 시세 조회 없음) */
export interface TacticalStrategySummary {
  portfolio_id: string;
  confirmed_regime: TacticalRegime | null;
  notify_enabled: boolean;
}

export const fetchTacticalStrategies = () => apiGet<TacticalStrategySummary[]>("/tactical");

export const fetchTacticalStatus = (portfolioId: string) =>
  apiGet<TacticalStatus>(`/tactical/${portfolioId}`);

export const upsertTacticalStrategy = (portfolioId: string, payload: TacticalStrategyPayload) =>
  apiPut<TacticalStatus>(`/tactical/${portfolioId}`, payload);

export const deleteTacticalStrategy = (portfolioId: string) =>
  apiDelete(`/tactical/${portfolioId}`);

/** fraction<1이면 현재 목표에서 제안 쪽으로 그만큼만 옮긴다(분할 적용 — 전술 자산만 있는 포트폴리오만) */
export const applyTacticalWeights = (portfolioId: string, fraction = 1) =>
  apiPost<TacticalStatus>(`/tactical/${portfolioId}/apply`, { fraction });

export const fetchTacticalBacktest = (portfolioId: string, years: number) =>
  apiGet<TacticalBacktestResult>(`/tactical/${portfolioId}/backtest`, { params: { years } });
