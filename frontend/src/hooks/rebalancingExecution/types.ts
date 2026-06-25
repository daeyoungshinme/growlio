import type { ExecutionResult, KisBalancePosition } from "@/api/rebalancing";

export type Phase = "confirm" | "executing" | "result";
export type BalanceLoadState = "idle" | "loading" | "loaded" | "error" | "not_found";
export type OrderType = "MARKET" | "LIMIT";
export type Strategy = "FULL" | "BUY_ONLY" | "TWO_PHASE";
export type PriceLoadState = "idle" | "loading" | "loaded" | "error";

export interface CashAnalysis {
  deposit: number | null;
  isOrderableKnown: boolean;
  sellProceeds: number | null;
  totalAvailable: number | null;
  buyCost: number | null;
  surplus: number | null;
}

export interface GlobalCashSummary {
  totalDeposit: number | null;
  totalSellProceeds: number | null;
  totalBuyCost: number | null;
  totalAvailable: number | null;
  surplus: number | null;
  isInsufficient: boolean;
  balancesLoaded: boolean;
}

export interface ExecutionState {
  liveBalances: Record<string, KisBalancePosition[]>;
  balanceState: Record<string, BalanceLoadState>;
  depositKrw: Record<string, number>;
  orderableKrw: Record<string, number>;
  priceState: PriceLoadState;
  priceLoadProgress: { loaded: number; total: number };
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  globalUsdRate: number | null;
  orderType: OrderType;
  strategy: Strategy;
  limitPriceOverrides: Record<string, number>;
  qtyOverrides: Record<string, number>;
  buyAccounts: Record<string, string[]>;
  selected: Set<string>;
  phase: Phase;
  results: ExecutionResult[];
  errorMsg: string | null;
  confirmed: boolean;
}

export type ExecutionAction =
  | { type: "BALANCES_START"; accountIds: string[] }
  | {
      type: "BALANCES_LOADED";
      balances: Record<string, KisBalancePosition[]>;
      deposits: Record<string, number>;
      orderables: Record<string, number>;
      states: Record<string, BalanceLoadState>;
    }
  | { type: "BALANCES_ERROR"; accountIds: string[] }
  | { type: "BALANCE_LOADING"; accountId: string }
  | {
      type: "BALANCE_LOADED";
      accountId: string;
      positions: KisBalancePosition[];
      deposit: number;
      orderable: number | null;
    }
  | { type: "BALANCE_ERROR"; accountId: string; is404: boolean }
  | { type: "PRICES_START"; total: number }
  | { type: "PRICES_PROGRESS"; loaded: number }
  | {
      type: "PRICES_DONE";
      krw: Record<string, number>;
      usd: Record<string, number>;
      usdRate: number | null;
    }
  | { type: "SET_ORDER_TYPE"; orderType: OrderType }
  | { type: "SET_STRATEGY"; strategy: Strategy }
  | { type: "SET_LIMIT_PRICE"; key: string; price: number }
  | { type: "SET_QTY"; key: string; qty: number }
  | { type: "SET_QTY_AND_SELECT"; key: string; qty: number }
  | { type: "TOGGLE_SELECTED"; key: string }
  | { type: "ADD_BUY_ACCOUNT"; ticker: string; accountId: string }
  | { type: "REMOVE_BUY_ACCOUNT"; ticker: string; accountId: string }
  | { type: "EXECUTE_START" }
  | { type: "EXECUTE_SUCCESS"; results: ExecutionResult[] }
  | { type: "EXECUTE_ERROR"; msg: string }
  | { type: "CONFIRM_CLICK" }
  | { type: "UNCONFIRM" }
  | { type: "BULK_SET_QTY"; entries: Array<{ key: string; qty: number }> };
