import { apiDelete, apiGet, apiPost, apiPut } from "./client";

export type TradeSide = "BUY" | "SELL";
export type PeriodType = "month" | "year";

export interface TradeRecord {
  id: string;
  account_id: string | null;
  side: TradeSide;
  ticker: string;
  market: string;
  name: string;
  qty: number;
  /** 항상 KRW — 해외 종목은 USD × 환율로 환산해 전송 */
  price_krw: number;
  fee: number | null;
  trade_date: string;
  notes: string | null;
  created_at: string;
}

export interface TradeCreate {
  account_id: string;
  side: TradeSide;
  ticker: string;
  market: string;
  name?: string;
  qty: number;
  price_krw: number;
  fee?: number;
  trade_date: string;
  notes?: string;
}

/** fee·notes는 null을 보내면 비운다(키를 빼면 기존 값 유지) */
export type TradeUpdate = Partial<
  Pick<TradeCreate, "side" | "qty" | "price_krw" | "trade_date">
> & {
  fee?: number | null;
  notes?: string | null;
};

/** ESTIMATED: 일별 스냅샷 보유수량·평단 변화로 추정 / MANUAL: 사용자가 기록한 매매로 계산 */
export type PurchaseSource = "ESTIMATED" | "MANUAL";

export interface PeriodPurchaseItem {
  account_id: string;
  account_name: string;
  ticker: string;
  market: string;
  name: string;
  source: PurchaseSource;
  bought_qty: number;
  bought_amount_krw: number;
  avg_buy_price_krw: number;
  held_qty: number;
  held_cost_krw: number;
  current_price_krw: number | null;
  value_krw: number;
  unrealized_pnl_krw: number;
  realized_pnl_krw: number;
  total_pnl_krw: number;
  cost_basis_krw: number;
  return_pct: number | null;
  first_buy_date: string | null;
  partially_sold: boolean;
  price_estimated: boolean;
}

export interface PeriodPurchaseSummary {
  start: string;
  end: string;
  items: PeriodPurchaseItem[];
  summary: {
    bought_amount_krw: number;
    held_cost_krw: number;
    value_krw: number;
    realized_pnl_krw: number;
    total_pnl_krw: number;
    return_pct: number | null;
  };
  tracking_started: { account_id: string; account_name: string; since: string }[];
}

export const fetchPeriodPurchases = (params: {
  period: PeriodType;
  year: number;
  month?: number;
  account_id?: string;
}) => apiGet<PeriodPurchaseSummary>("/trades/period-summary", { params });

export const fetchTrades = (params?: { account_id?: string; ticker?: string; market?: string }) =>
  apiGet<TradeRecord[]>("/trades", { params });

export const createTrade = (data: TradeCreate) => apiPost<TradeRecord>("/trades", data);

export const updateTrade = (id: string, data: TradeUpdate) =>
  apiPut<TradeRecord>(`/trades/${id}`, data);

export const deleteTrade = (id: string) => apiDelete(`/trades/${id}`);
