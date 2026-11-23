import { apiDelete, apiGet, apiPost, apiPut } from "./client";

/**
 * 낙폭 추매 안내(plans/147·148) — 적립과 별도인 여윳돈(사용자당 하나)을 지수별 규칙 몫·낙폭 구간으로 나눠 안내한다.
 * 포트폴리오와 무관하고, 주문은 하지 않는다.
 */
export type DipBuyIndex = "QQQ" | "SPY";
export type DipBuyTierState = "DONE" | "DUE" | "WAITING";
/** ON_REACH: 구간 도달 다음 날 아침 / MONTHLY_DAY: 매달 정한 날(휴장이면 다음 거래일) */
export type DipBuyNotifyMode = "ON_REACH" | "MONTHLY_DAY";

export const DIP_BUY_INDEXES: readonly DipBuyIndex[] = ["QQQ", "SPY"];

export interface DipBuyTierInput {
  drawdown_pct: number;
  ratio_pct: number;
}

export interface DipBuyTierStatus extends DipBuyTierInput {
  tier: number;
  amount_krw: number;
  state: DipBuyTierState;
  done_amount_krw: number | null;
}

/** 안내 금액으로 이 ETF만 산다면 — 같은 지수 ETF끼리는 대안(이 중 하나로) */
export interface DipBuyEtf {
  ticker: string;
  name: string;
  market: string;
  price_krw: number;
  shares: number;
  amount_krw: number;
  /** 해외 종목이면 필요 달러(실환율일 때만) */
  amount_usd: number | null;
  /** 해외 종목 1주 달러가(실환율일 때만). 저장된 옛 응답엔 없을 수 있다 */
  price_usd?: number | null;
}

export interface DipBuySettings {
  reserve_krw: number;
  notify_mode: DipBuyNotifyMode;
  notify_day: number | null;
  is_active: boolean;
}

export interface DipBuyRule {
  id: string;
  index_ticker: DipBuyIndex;
  allocation_pct: number;
  is_active: boolean;
  /** 이 규칙 몫(사이클 중이면 첫 추매 때 고정한 기준액) */
  base_krw: number;
  spent_krw: number;
  remaining_krw: number;
  tiers: DipBuyTierStatus[];
  /** 52주 고점 대비(%, 0 이하). null = 확인 불가 */
  drawdown_pct: number | null;
  due_amount_krw: number;
  due_tiers: number[];
  etfs: DipBuyEtf[];
}

export interface DipBuyStatus {
  settings: DipBuySettings | null;
  rules: DipBuyRule[];
  /** 알림 방식이 매달 정한 날일 때 다음 알림일 */
  next_notify_date: string | null;
  due_amount_krw: number;
  /** 전술 연동 적립 자동매수가 방어 국면이라 보류 중인 포트폴리오 */
  dca_held_portfolios: string[];
  /** 추천 후보 ETF 중 QQQ·SPY 지수 추종 ETF가 있는지 */
  has_candidates: boolean;
  /** 지수별 52주 고점 대비 낙폭(규칙이 없는 지수도) — null = 확인 불가 */
  index_drawdowns: Partial<Record<DipBuyIndex, number | null>>;
  /** 고점 대비 이 % 이내로 회복하면 완료 기록을 지우고 다음 하락을 기다린다 */
  reset_drawdown_pct: number;
}

export type DipBuySettingsInput = DipBuySettings;

export interface DipBuyRuleInput {
  index_ticker: DipBuyIndex;
  allocation_pct: number;
  tiers: DipBuyTierInput[];
  is_active: boolean;
  /** 배분 합계가 100%를 넘으면 다른 규칙 배분을 비율대로 줄여 맞춘다 */
  shrink_others?: boolean;
}

/** 백엔드 `dip_buy_calculator.DEFAULT_TIERS`와 같은 기본 구간 */
export const DEFAULT_DIP_BUY_TIERS: DipBuyTierInput[] = [
  { drawdown_pct: 10, ratio_pct: 20 },
  { drawdown_pct: 20, ratio_pct: 30 },
  { drawdown_pct: 30, ratio_pct: 50 },
];

/** 낙폭 추매 ↔ 전술 웅덩이 매수 역할 구분 — 두 화면(적립 계획 낙폭 추매·전술 탭)이 같은 문장을 쓴다(plans/150 C3) */
export const DIP_BUY_VS_TACTICAL_NOTE =
  "낙폭 추매는 계좌 밖 여윳돈으로 더 사는 안내, 웅덩이 매수는 포트폴리오 안 현금 비중을 옮기는 전술이에요.";

export const DIP_BUY_INDEX_LABEL: Record<DipBuyIndex, string> = {
  QQQ: "나스닥100 (QQQ)",
  SPY: "S&P500 (SPY)",
};

export const fetchDipBuyStatus = () => apiGet<DipBuyStatus>("/invest/dip-buy");

export const upsertDipBuySettings = (data: DipBuySettingsInput) =>
  apiPut<void>("/invest/dip-buy/settings", data);

export const createDipBuyRule = (data: DipBuyRuleInput) =>
  apiPost<void>("/invest/dip-buy/rules", data);

export const updateDipBuyRule = (ruleId: string, data: DipBuyRuleInput) =>
  apiPut<void>(`/invest/dip-buy/rules/${ruleId}`, data);

export const deleteDipBuyRule = (ruleId: string) =>
  apiDelete<void>(`/invest/dip-buy/rules/${ruleId}`);

export const completeDipBuy = (ruleId: string, amountKrw: number | null) =>
  apiPost<void>(`/invest/dip-buy/rules/${ruleId}/complete`, { amount_krw: amountKrw });
