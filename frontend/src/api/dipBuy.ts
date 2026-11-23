import { apiDelete, apiGet, apiPost, apiPut } from "./client";

/** 낙폭 추매 안내(plans/147) — 적립과 별도인 여윳돈을 지수 낙폭 구간별로 나눠 안내한다. 주문은 하지 않는다. */
export type DipBuyIndex = "QQQ" | "SPY";
export type DipBuyTierState = "DONE" | "DUE" | "WAITING";

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

export interface DipBuyItem {
  ticker: string;
  name: string;
  market: string;
  shares: number;
  amount_krw: number;
  price_krw: number;
  /** 해외 종목이면 필요 달러(실환율일 때만) */
  amount_usd: number | null;
}

export interface DipBuyPlan {
  id: string;
  portfolio_id: string;
  portfolio_name: string;
  is_active: boolean;
  index_ticker: DipBuyIndex;
  reserve_krw: number;
  cycle_base_krw: number | null;
  tiers: DipBuyTierStatus[];
  /** 52주 고점 대비(%, 0 이하). null = 확인 불가 */
  drawdown_pct: number | null;
  /** 정기 적립식 자동매수가 없으면 false — 종목 분할·적립일 안내를 못 한다 */
  has_dca_schedule: boolean;
  next_run_date: string | null;
  is_run_day: boolean;
  due_amount_krw: number;
  due_tiers: number[];
  items: DipBuyItem[];
  leftover_krw: number;
}

export interface DipBuyStatus {
  plans: DipBuyPlan[];
  /** 고점 대비 이 % 이내로 회복하면 완료 기록을 지우고 다음 하락을 기다린다 */
  reset_drawdown_pct: number;
}

export interface DipBuyPlanInput {
  index_ticker: DipBuyIndex;
  reserve_krw: number;
  tiers: DipBuyTierInput[];
  is_active: boolean;
}

/** 백엔드 `dip_buy_calculator.DEFAULT_TIERS`와 같은 기본 구간 */
export const DEFAULT_DIP_BUY_TIERS: DipBuyTierInput[] = [
  { drawdown_pct: 10, ratio_pct: 20 },
  { drawdown_pct: 20, ratio_pct: 30 },
  { drawdown_pct: 30, ratio_pct: 50 },
];

export const fetchDipBuyStatus = () => apiGet<DipBuyStatus>("/invest/dip-buy");

export const upsertDipBuyPlan = (portfolioId: string, data: DipBuyPlanInput) =>
  apiPut<void>(`/invest/dip-buy/${portfolioId}`, data);

export const completeDipBuy = (portfolioId: string, amountKrw: number | null) =>
  apiPost<void>(`/invest/dip-buy/${portfolioId}/complete`, { amount_krw: amountKrw });

export const deleteDipBuyPlan = (portfolioId: string) =>
  apiDelete<void>(`/invest/dip-buy/${portfolioId}`);
