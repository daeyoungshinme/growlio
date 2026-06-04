import { useEffect, useReducer } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AssetAccount } from "../api/assets";
import { extractErrorMessage } from "../utils/error";
import { invalidateSyncData } from "../utils/queryInvalidation";
import { OVERSEAS_MARKET_SET, isOverseasMarket } from "../constants/markets";
import {
  ExecutionOrderItem,
  ExecutionResult,
  KisBalancePosition,
  RebalancingAnalysis,
  RebalancingItem,
  executeRebalancing,
} from "../api/rebalancing";
import { useRebalancingBalances } from "./useRebalancingBalances";
import { useRebalancingPrices } from "./useRebalancingPrices";

export type Phase = "confirm" | "executing" | "result";
export type BalanceLoadState = "idle" | "loading" | "loaded" | "error" | "not_found";
export type OrderType = "MARKET" | "LIMIT";
export type PriceLoadState = "idle" | "loading" | "loaded" | "error";

export interface CashAnalysis {
  deposit: number | null;
  sellProceeds: number | null;
  totalAvailable: number | null;
  buyCost: number | null;
  surplus: number | null;
}

export interface ExecutionState {
  liveBalances: Record<string, KisBalancePosition[]>;
  balanceState: Record<string, BalanceLoadState>;
  depositKrw: Record<string, number>;
  priceState: PriceLoadState;
  priceLoadProgress: { loaded: number; total: number };
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  globalUsdRate: number | null;
  orderType: OrderType;
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
  | { type: "BALANCES_LOADED"; balances: Record<string, KisBalancePosition[]>; deposits: Record<string, number>; states: Record<string, BalanceLoadState> }
  | { type: "BALANCES_ERROR"; accountIds: string[] }
  | { type: "BALANCE_LOADING"; accountId: string }
  | { type: "BALANCE_LOADED"; accountId: string; positions: KisBalancePosition[]; deposit: number }
  | { type: "BALANCE_ERROR"; accountId: string; is404: boolean }
  | { type: "PRICES_START"; total: number }
  | { type: "PRICES_PROGRESS"; loaded: number }
  | { type: "PRICES_DONE"; krw: Record<string, number>; usd: Record<string, number>; usdRate: number | null }
  | { type: "SET_ORDER_TYPE"; orderType: OrderType }
  | { type: "SET_LIMIT_PRICE"; key: string; price: number }
  | { type: "SET_QTY"; key: string; qty: number }
  | { type: "SET_QTY_AND_SELECT"; key: string; qty: number }
  | { type: "TOGGLE_SELECTED"; key: string }
  | { type: "ADD_BUY_ACCOUNT"; ticker: string; accountId: string }
  | { type: "REMOVE_BUY_ACCOUNT"; ticker: string; accountId: string }
  | { type: "EXECUTE_START" }
  | { type: "EXECUTE_SUCCESS"; results: ExecutionResult[] }
  | { type: "EXECUTE_ERROR"; msg: string }
  | { type: "CONFIRM_CLICK" };

export function executionReducer(state: ExecutionState, action: ExecutionAction): ExecutionState {
  switch (action.type) {
    case "BALANCES_START":
      return {
        ...state,
        balanceState: Object.fromEntries(action.accountIds.map((id) => [id, "loading" as BalanceLoadState])),
      };
    case "BALANCES_LOADED":
      return {
        ...state,
        liveBalances: action.balances,
        depositKrw: action.deposits,
        balanceState: { ...state.balanceState, ...action.states },
      };
    case "BALANCES_ERROR":
      return {
        ...state,
        balanceState: Object.fromEntries(action.accountIds.map((id) => [id, "error" as BalanceLoadState])),
      };
    case "BALANCE_LOADING":
      return { ...state, balanceState: { ...state.balanceState, [action.accountId]: "loading" } };
    case "BALANCE_LOADED":
      return {
        ...state,
        liveBalances: { ...state.liveBalances, [action.accountId]: action.positions },
        depositKrw: { ...state.depositKrw, [action.accountId]: action.deposit },
        balanceState: { ...state.balanceState, [action.accountId]: "loaded" },
      };
    case "BALANCE_ERROR":
      return {
        ...state,
        balanceState: {
          ...state.balanceState,
          [action.accountId]: action.is404 ? "not_found" : "error",
        },
      };
    case "PRICES_START":
      return { ...state, priceState: "loading", priceLoadProgress: { loaded: 0, total: action.total } };
    case "PRICES_PROGRESS":
      return { ...state, priceLoadProgress: { ...state.priceLoadProgress, loaded: action.loaded } };
    case "PRICES_DONE":
      return {
        ...state,
        livePricesKrw: action.krw,
        livePricesUsd: action.usd,
        globalUsdRate: action.usdRate ?? state.globalUsdRate,
        priceState: Object.keys(action.krw).length > 0 ? "loaded" : "error",
      };
    case "SET_ORDER_TYPE":
      return { ...state, orderType: action.orderType };
    case "SET_LIMIT_PRICE":
      return { ...state, limitPriceOverrides: { ...state.limitPriceOverrides, [action.key]: Math.max(0, action.price) } };
    case "SET_QTY":
      return { ...state, qtyOverrides: { ...state.qtyOverrides, [action.key]: Math.max(0, action.qty) } };
    case "SET_QTY_AND_SELECT": {
      const next = new Set(state.selected);
      if (action.qty > 0) next.add(action.key); else next.delete(action.key);
      return { ...state, qtyOverrides: { ...state.qtyOverrides, [action.key]: Math.max(0, action.qty) }, selected: next };
    }
    case "TOGGLE_SELECTED": {
      const next = new Set(state.selected);
      if (next.has(action.key)) next.delete(action.key); else next.add(action.key);
      return { ...state, selected: next };
    }
    case "ADD_BUY_ACCOUNT":
      return {
        ...state,
        buyAccounts: { ...state.buyAccounts, [action.ticker]: [...(state.buyAccounts[action.ticker] ?? []), action.accountId] },
        qtyOverrides: { ...state.qtyOverrides, [`buy_${action.ticker}_${action.accountId}`]: 0 },
      };
    case "REMOVE_BUY_ACCOUNT": {
      const key = `buy_${action.ticker}_${action.accountId}`;
      const next = new Set(state.selected);
      next.delete(key);
      const nextQty = { ...state.qtyOverrides };
      delete nextQty[key];
      return {
        ...state,
        buyAccounts: { ...state.buyAccounts, [action.ticker]: (state.buyAccounts[action.ticker] ?? []).filter((id) => id !== action.accountId) },
        selected: next,
        qtyOverrides: nextQty,
      };
    }
    case "EXECUTE_START":
      return { ...state, phase: "executing", errorMsg: null, confirmed: false };
    case "EXECUTE_SUCCESS":
      return { ...state, phase: "result", results: action.results };
    case "EXECUTE_ERROR":
      return { ...state, phase: "confirm", errorMsg: action.msg };
    case "CONFIRM_CLICK":
      return { ...state, confirmed: true };
    default:
      return state;
  }
}

export { isOverseasMarket, OVERSEAS_MARKET_SET };

export function getActionableItems(analysis: RebalancingAnalysis): RebalancingItem[] {
  return analysis.items.filter(
    (i) =>
      i.ticker !== "CASH" &&
      i.market !== "KR_PROPERTY" &&
      i.shares_to_trade !== null &&
      Math.abs(i.shares_to_trade) >= 1
  );
}

function computeInitialBuyAndSelected(
  analysis: RebalancingAnalysis,
  kisAccounts: AssetAccount[]
): { buyAccounts: Record<string, string[]>; selected: Set<string> } {
  const actionableItems = getActionableItems(analysis);
  const defaultAccId = kisAccounts[0]?.id ?? "";

  function getPrimaryAccountId(ticker: string): string {
    const infos = (analysis.ticker_account_map[ticker] ?? []).filter((a) => a.asset_type === "STOCK_KIS");
    if (infos.length === 0) return defaultAccId;
    return infos.reduce((best, a) => (a.quantity > best.quantity ? a : best), infos[0]).account_id;
  }

  const buyAccounts: Record<string, string[]> = {};
  const selected = new Set<string>();

  if (!defaultAccId) return { buyAccounts, selected };

  actionableItems.forEach((i) => {
    if ((i.shares_to_trade ?? 0) > 0) {
      buyAccounts[i.ticker] = [getPrimaryAccountId(i.ticker)];
    }
  });

  actionableItems.forEach((i) => {
    if ((i.shares_to_trade ?? 0) < 0) {
      (analysis.ticker_account_map[i.ticker] ?? [])
        .filter((a) => a.asset_type === "STOCK_KIS")
        .forEach((a) => selected.add(`sell_${i.ticker}_${a.account_id}`));
    } else if ((i.shares_to_trade ?? 0) > 0) {
      const accId = getPrimaryAccountId(i.ticker) || defaultAccId;
      if (accId) selected.add(`buy_${i.ticker}_${accId}`);
    }
  });

  return { buyAccounts, selected };
}

interface UseRebalancingExecutionParams {
  portfolioId: string;
  analysis: RebalancingAnalysis;
  accounts: AssetAccount[];
  onExecuted?: (results: ExecutionResult[]) => void;
}

export function useRebalancingExecution({ portfolioId, analysis, accounts, onExecuted }: UseRebalancingExecutionParams) {
  const queryClient = useQueryClient();
  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM");

  const [state, dispatch] = useReducer(
    executionReducer,
    { analysis, kisAccounts },
    ({ analysis: a, kisAccounts: kas }) => {
      const { buyAccounts, selected } = computeInitialBuyAndSelected(a, kas);
      return {
        liveBalances: {},
        balanceState: {},
        depositKrw: {},
        priceState: "idle" as PriceLoadState,
        priceLoadProgress: { loaded: 0, total: 0 },
        livePricesKrw: {},
        livePricesUsd: {},
        globalUsdRate: null,
        orderType: "MARKET" as OrderType,
        limitPriceOverrides: {},
        qtyOverrides: {},
        buyAccounts,
        selected,
        phase: "confirm" as Phase,
        results: [],
        errorMsg: null,
        confirmed: false,
      };
    }
  );

  const { liveBalances, qtyOverrides, buyAccounts, selected, orderType, limitPriceOverrides, livePricesKrw, livePricesUsd, globalUsdRate } = state;

  const actionableItems = getActionableItems(analysis);
  const { loadLiveBalance, loadAllLiveBalances } = useRebalancingBalances(dispatch, kisAccounts);
  const { loadAllPrices } = useRebalancingPrices(dispatch, analysis);

  function getAccountQuantity(ticker: string, accountId: string): number {
    const livePos = liveBalances[accountId]?.find((p) => p.ticker === ticker);
    if (livePos !== undefined) return livePos.quantity;
    return (analysis.ticker_account_map[ticker] ?? []).find((a) => a.account_id === accountId)?.quantity ?? 0;
  }

  function accountHoldsTicker(ticker: string, accountId: string): boolean {
    if (liveBalances[accountId]) {
      return liveBalances[accountId].some((p) => p.ticker === ticker && p.quantity > 0);
    }
    return (analysis.ticker_account_map[ticker] ?? []).some(
      (a) => a.account_id === accountId && (a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM") && a.quantity > 0
    );
  }

  function getLimitPriceNative(key: string, ticker: string, market: string): number {
    if (key in limitPriceOverrides) return limitPriceOverrides[key];
    return isOverseasMarket(market) ? (livePricesUsd[ticker] ?? 0) : (livePricesKrw[ticker] ?? 0);
  }

  function getEstimateKrw(key: string, ticker: string, market: string, qty: number): number | null {
    if (orderType === "LIMIT") {
      const native = getLimitPriceNative(key, ticker, market);
      if (native <= 0) return null;
      if (isOverseasMarket(market)) return globalUsdRate != null ? native * globalUsdRate * qty : null;
      return native * qty;
    }
    const priceKrw = livePricesKrw[ticker] ?? null;
    return priceKrw != null ? priceKrw * qty : null;
  }

  function getSellRows(accountId: string): { item: RebalancingItem; currentQty: number; suggestedQty: number }[] {
    const rows: { item: RebalancingItem; currentQty: number; suggestedQty: number }[] = [];
    for (const item of actionableItems) {
      if ((item.shares_to_trade ?? 0) >= 0) continue;
      if (!accountHoldsTicker(item.ticker, accountId)) continue;
      const currentQty = getAccountQuantity(item.ticker, accountId);
      if (currentQty <= 0) continue;
      const allKisQty = kisAccounts.reduce((sum, acc) => sum + getAccountQuantity(item.ticker, acc.id), 0);
      const suggested = allKisQty > 0
        ? Math.round(Math.abs(item.shares_to_trade!) * currentQty / allKisQty)
        : Math.abs(Math.round(item.shares_to_trade!));
      if (suggested > 0) rows.push({ item, currentQty, suggestedQty: suggested });
    }
    return rows;
  }

  function getBuyRows(accountId: string): { item: RebalancingItem; suggestedQty: number; currentQty: number }[] {
    return actionableItems
      .filter((i) => (i.shares_to_trade ?? 0) > 0 && (buyAccounts[i.ticker] ?? []).includes(accountId))
      .map((i) => ({
        item: i,
        suggestedQty: Math.abs(Math.round(i.shares_to_trade!)),
        currentQty: getAccountQuantity(i.ticker, accountId),
      }));
  }

  function getBuyTotalInfo(ticker: string): { allocated: number; needed: number } {
    const item = actionableItems.find((i) => i.ticker === ticker);
    const needed = Math.abs(Math.round(item?.shares_to_trade ?? 0));
    const allocated = (buyAccounts[ticker] ?? []).reduce((sum, accId) => {
      const key = `buy_${ticker}_${accId}`;
      if (!selected.has(key)) return sum;
      return sum + (qtyOverrides[key] ?? needed);
    }, 0);
    return { allocated, needed };
  }

  function buildOrders(): ExecutionOrderItem[] {
    const orders: ExecutionOrderItem[] = [];
    kisAccounts.forEach((acc) => {
      getSellRows(acc.id).forEach(({ item, suggestedQty }) => {
        const key = `sell_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({
            ticker: item.ticker, name: item.name, market: item.market, side: "SELL", quantity: qty, account_id: acc.id,
            order_type: orderType,
            limit_price: orderType === "LIMIT" ? getLimitPriceNative(key, item.ticker, item.market) || null : null,
          });
      });
      getBuyRows(acc.id).forEach(({ item, suggestedQty }) => {
        const key = `buy_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({
            ticker: item.ticker, name: item.name, market: item.market, side: "BUY", quantity: qty, account_id: acc.id,
            order_type: orderType,
            limit_price: orderType === "LIMIT" ? getLimitPriceNative(key, item.ticker, item.market) || null : null,
          });
      });
    });
    return orders;
  }

  function getCashAnalysis(accountId: string): CashAnalysis {
    const deposit = state.depositKrw[accountId] ?? null;
    let sellProceeds: number | null = 0;
    for (const { item, suggestedQty } of getSellRows(accountId)) {
      const key = `sell_${item.ticker}_${accountId}`;
      if (!selected.has(key)) continue;
      const qty = qtyOverrides[key] ?? suggestedQty;
      const est = getEstimateKrw(key, item.ticker, item.market, qty);
      if (est === null) { sellProceeds = null; break; }
      sellProceeds = (sellProceeds ?? 0) + est;
    }
    let buyCost: number | null = 0;
    for (const { item, suggestedQty } of getBuyRows(accountId)) {
      const key = `buy_${item.ticker}_${accountId}`;
      if (!selected.has(key)) continue;
      const qty = qtyOverrides[key] ?? suggestedQty;
      const est = getEstimateKrw(key, item.ticker, item.market, qty);
      if (est === null) { buyCost = null; break; }
      buyCost = (buyCost ?? 0) + est;
    }
    const totalAvailable = deposit !== null && sellProceeds !== null ? deposit + sellProceeds : null;
    const surplus = totalAvailable !== null && buyCost !== null ? totalAvailable - buyCost : null;
    return { deposit, sellProceeds, totalAvailable, buyCost, surplus };
  }

  function getAccountSummary(accountId: string) {
    const sells = getSellRows(accountId).filter((r) => selected.has(`sell_${r.item.ticker}_${accountId}`)).length;
    const buys = getBuyRows(accountId).filter((r) => selected.has(`buy_${r.item.ticker}_${accountId}`)).length;
    return { sells, buys };
  }

  useEffect(() => {
    loadAllLiveBalances();
    loadAllPrices();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const orders = buildOrders();
  const hasRealAccount = orders.some((o) => {
    const acc = kisAccounts.find((a) => a.id === o.account_id);
    return acc && !acc.is_mock_mode;
  });

  async function handleExecute() {
    if (orders.length === 0) return;
    dispatch({ type: "EXECUTE_START" });
    try {
      const res = await executeRebalancing(portfolioId, { account_id: null, orders });
      dispatch({ type: "EXECUTE_SUCCESS", results: res });
      await invalidateSyncData(queryClient);
      onExecuted?.(res);
    } catch (e: unknown) {
      dispatch({ type: "EXECUTE_ERROR", msg: extractErrorMessage(e, "주문 실행 중 오류가 발생했습니다.") });
    }
  }

  return {
    state,
    dispatch,
    kisAccounts,
    actionableItems,
    orders,
    hasRealAccount,
    getAccountQuantity,
    getSellRows,
    getBuyRows,
    getBuyTotalInfo,
    getAccountSummary,
    getCashAnalysis,
    getLimitPriceNative,
    getEstimateKrw,
    loadLiveBalance,
    handleExecute,
  };
}

export type RebalancingExecutionHook = ReturnType<typeof useRebalancingExecution>;
