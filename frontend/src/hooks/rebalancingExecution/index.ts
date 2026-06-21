import { createContext, useContext, useEffect, useMemo, useReducer } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import { extractErrorMessage } from "@/utils/error";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { triggerHaptic } from "../useHaptic";
import { OVERSEAS_MARKET_SET, isOverseasMarket } from "@/constants/markets";
import { CASH_TICKER, KR_PROPERTY_MARKET } from "@/constants/assets";
import {
  type ExecutionOrderItem,
  type ExecutionResult,
  type RebalancingAnalysis,
  type RebalancingItem,
  executeRebalancing,
} from "@/api/rebalancing";
import { useRebalancingBalances } from "../useRebalancingBalances";
import { useRebalancingPrices } from "../useRebalancingPrices";
import type { CashAnalysis, GlobalCashSummary, OrderType, Phase, PriceLoadState } from "./types";
import { executionReducer } from "./reducer";

export type {
  Phase,
  BalanceLoadState,
  OrderType,
  PriceLoadState,
  CashAnalysis,
  GlobalCashSummary,
  ExecutionState,
  ExecutionAction,
} from "./types";
export { executionReducer } from "./reducer";
export { isOverseasMarket, OVERSEAS_MARKET_SET };

export function getActionableItems(analysis: RebalancingAnalysis): RebalancingItem[] {
  return analysis.items.filter(
    (i) =>
      i.ticker !== CASH_TICKER &&
      i.market !== KR_PROPERTY_MARKET &&
      i.shares_to_trade !== null &&
      Math.abs(i.shares_to_trade) >= 1,
  );
}

function computeInitialBuyAndSelected(
  analysis: RebalancingAnalysis,
  kisAccounts: AssetAccount[],
): { buyAccounts: Record<string, string[]>; selected: Set<string> } {
  const actionableItems = getActionableItems(analysis);
  const defaultAccId = kisAccounts[0]?.id ?? "";

  function getPrimaryAccountId(ticker: string): string {
    const infos = (analysis.ticker_account_map[ticker] ?? []).filter(
      (a) => a.asset_type === "STOCK_KIS",
    );
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

export function useRebalancingExecution({
  portfolioId,
  analysis,
  accounts,
  onExecuted,
}: UseRebalancingExecutionParams) {
  const queryClient = useQueryClient();
  const kisAccounts = accounts.filter(
    (a) => a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM",
  );

  const [state, dispatch] = useReducer(
    executionReducer,
    { analysis, kisAccounts },
    ({ analysis: a, kisAccounts: kas }) => {
      const { buyAccounts, selected } = computeInitialBuyAndSelected(a, kas);
      return {
        liveBalances: {},
        balanceState: {},
        depositKrw: {},
        orderableKrw: {},
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
    },
  );

  const {
    liveBalances,
    qtyOverrides,
    buyAccounts,
    selected,
    orderType,
    limitPriceOverrides,
    livePricesKrw,
    livePricesUsd,
    globalUsdRate,
  } = state;

  const actionableItems = getActionableItems(analysis);
  const { loadLiveBalance, loadAllLiveBalances } = useRebalancingBalances(dispatch, kisAccounts);
  const { loadAllPrices } = useRebalancingPrices(dispatch, analysis);

  function getAccountQuantity(ticker: string, accountId: string): number {
    const livePos = liveBalances[accountId]?.find((p) => p.ticker === ticker);
    if (livePos !== undefined) return livePos.quantity;
    return (
      (analysis.ticker_account_map[ticker] ?? []).find((a) => a.account_id === accountId)
        ?.quantity ?? 0
    );
  }

  function accountHoldsTicker(ticker: string, accountId: string): boolean {
    if (liveBalances[accountId]) {
      return liveBalances[accountId].some((p) => p.ticker === ticker && p.quantity > 0);
    }
    return (analysis.ticker_account_map[ticker] ?? []).some(
      (a) =>
        a.account_id === accountId &&
        (a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM") &&
        a.quantity > 0,
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
      if (isOverseasMarket(market))
        return globalUsdRate != null ? native * globalUsdRate * qty : null;
      return native * qty;
    }
    const priceKrw = livePricesKrw[ticker] ?? null;
    return priceKrw != null ? priceKrw * qty : null;
  }

  function getSellRows(
    accountId: string,
  ): { item: RebalancingItem; currentQty: number; suggestedQty: number }[] {
    const rows: { item: RebalancingItem; currentQty: number; suggestedQty: number }[] = [];
    for (const item of actionableItems) {
      if ((item.shares_to_trade ?? 0) >= 0) continue;
      if (!accountHoldsTicker(item.ticker, accountId)) continue;
      const currentQty = getAccountQuantity(item.ticker, accountId);
      if (currentQty <= 0) continue;
      const allKisQty = kisAccounts.reduce(
        (sum, acc) => sum + getAccountQuantity(item.ticker, acc.id),
        0,
      );
      const totalSuggested = Math.abs(Math.round(item.shares_to_trade!));
      const suggested =
        allKisQty > 0
          ? Math.round((totalSuggested * currentQty) / allKisQty)
          : totalSuggested;
      if (suggested > 0) rows.push({ item, currentQty, suggestedQty: suggested });
    }
    return rows;
  }

  function getBuyRows(
    accountId: string,
  ): { item: RebalancingItem; suggestedQty: number; currentQty: number }[] {
    return actionableItems
      .filter(
        (i) => (i.shares_to_trade ?? 0) > 0 && (buyAccounts[i.ticker] ?? []).includes(accountId),
      )
      .map((i) => {
        const suggestedQty = Math.abs(Math.round(i.shares_to_trade!));
        return { item: i, suggestedQty, currentQty: getAccountQuantity(i.ticker, accountId) };
      });
  }

  const sellRowsByAccount = useMemo(() => {
    const map: Record<string, ReturnType<typeof getSellRows>> = {};
    for (const acc of kisAccounts) map[acc.id] = getSellRows(acc.id);
    return map;
    // getSellRows는 컴포넌트 스코프 함수 — dep 추가 시 무한 재계산. 실제 의존값은 이미 포함됨.
  }, [actionableItems, liveBalances, kisAccounts]); // eslint-disable-line react-hooks/exhaustive-deps

  const buyRowsByAccount = useMemo(() => {
    const map: Record<string, ReturnType<typeof getBuyRows>> = {};
    for (const acc of kisAccounts) map[acc.id] = getBuyRows(acc.id);
    return map;
    // getBuyRows는 컴포넌트 스코프 함수 — dep 추가 시 무한 재계산. 실제 의존값은 이미 포함됨.
  }, [actionableItems, liveBalances, buyAccounts, kisAccounts]); // eslint-disable-line react-hooks/exhaustive-deps

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
      (sellRowsByAccount[acc.id] ?? []).forEach(({ item, suggestedQty }) => {
        const key = `sell_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({
            ticker: item.ticker,
            name: item.name,
            market: item.market,
            side: "SELL",
            quantity: qty,
            account_id: acc.id,
            order_type: orderType,
            limit_price:
              orderType === "LIMIT"
                ? getLimitPriceNative(key, item.ticker, item.market) || null
                : null,
          });
      });
      (buyRowsByAccount[acc.id] ?? []).forEach(({ item, suggestedQty }) => {
        const key = `buy_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({
            ticker: item.ticker,
            name: item.name,
            market: item.market,
            side: "BUY",
            quantity: qty,
            account_id: acc.id,
            order_type: orderType,
            limit_price:
              orderType === "LIMIT"
                ? getLimitPriceNative(key, item.ticker, item.market) || null
                : null,
          });
      });
    });
    return orders;
  }

  function getCashAnalysis(accountId: string): CashAnalysis {
    const isOrderableKnown = accountId in state.orderableKrw;
    const deposit = isOrderableKnown
      ? (state.orderableKrw[accountId] ?? null)
      : (state.depositKrw[accountId] ?? null);
    let sellProceeds: number | null = 0;
    for (const { item, suggestedQty } of sellRowsByAccount[accountId] ?? []) {
      const key = `sell_${item.ticker}_${accountId}`;
      if (!selected.has(key)) continue;
      const qty = qtyOverrides[key] ?? suggestedQty;
      const est = getEstimateKrw(key, item.ticker, item.market, qty);
      if (est === null) {
        sellProceeds = null;
        break;
      }
      sellProceeds = (sellProceeds ?? 0) + est;
    }
    let buyCost: number | null = 0;
    for (const { item, suggestedQty } of buyRowsByAccount[accountId] ?? []) {
      const key = `buy_${item.ticker}_${accountId}`;
      if (!selected.has(key)) continue;
      const qty = qtyOverrides[key] ?? suggestedQty;
      const est = getEstimateKrw(key, item.ticker, item.market, qty);
      if (est === null) {
        buyCost = null;
        break;
      }
      buyCost = (buyCost ?? 0) + est;
    }
    const totalAvailable =
      deposit !== null && sellProceeds !== null ? deposit + sellProceeds : null;
    const surplus = totalAvailable !== null && buyCost !== null ? totalAvailable - buyCost : null;
    return { deposit, isOrderableKnown, sellProceeds, totalAvailable, buyCost, surplus };
  }

  const globalCashSummary = useMemo((): GlobalCashSummary => {
    const balancesLoaded = kisAccounts.some((acc) => state.balanceState[acc.id] === "loaded");
    if (!balancesLoaded) {
      return {
        totalDeposit: null,
        totalSellProceeds: null,
        totalBuyCost: null,
        totalAvailable: null,
        surplus: null,
        isInsufficient: false,
        balancesLoaded: false,
      };
    }

    let totalDeposit = 0;
    for (const acc of kisAccounts) {
      const useOrderable = acc.id in state.orderableKrw;
      totalDeposit += useOrderable
        ? (state.orderableKrw[acc.id] ?? 0)
        : (state.depositKrw[acc.id] ?? 0);
    }

    let totalSellProceeds: number | null = 0;
    loop: for (const acc of kisAccounts) {
      for (const { item, suggestedQty } of sellRowsByAccount[acc.id] ?? []) {
        const key = `sell_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) continue;
        const qty = qtyOverrides[key] ?? suggestedQty;
        const est = getEstimateKrw(key, item.ticker, item.market, qty);
        if (est === null) {
          totalSellProceeds = null;
          break loop;
        }
        totalSellProceeds = (totalSellProceeds ?? 0) + est;
      }
    }

    let totalBuyCost: number | null = 0;
    loop2: for (const acc of kisAccounts) {
      for (const { item, suggestedQty } of buyRowsByAccount[acc.id] ?? []) {
        const key = `buy_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) continue;
        const qty = qtyOverrides[key] ?? suggestedQty;
        const est = getEstimateKrw(key, item.ticker, item.market, qty);
        if (est === null) {
          totalBuyCost = null;
          break loop2;
        }
        totalBuyCost = (totalBuyCost ?? 0) + est;
      }
    }

    const totalAvailable =
      totalSellProceeds !== null ? totalDeposit + totalSellProceeds : null;
    const surplus =
      totalAvailable !== null && totalBuyCost !== null ? totalAvailable - totalBuyCost : null;
    return {
      totalDeposit,
      totalSellProceeds,
      totalBuyCost,
      totalAvailable,
      surplus,
      isInsufficient: surplus !== null && surplus < 0,
      balancesLoaded: true,
    };
    // getEstimateKrw는 훅 스코프 함수 — 실제 의존값(orderType, prices, limitPriceOverrides)은 아래에 포함됨.
  }, [kisAccounts, state.balanceState, state.depositKrw, state.orderableKrw, sellRowsByAccount, buyRowsByAccount, selected, qtyOverrides, livePricesKrw, livePricesUsd, globalUsdRate, orderType, limitPriceOverrides]); // eslint-disable-line react-hooks/exhaustive-deps

  function autoAdjustForCash() {
    if (!globalCashSummary.balancesLoaded || !globalCashSummary.isInsufficient) return;
    if (globalCashSummary.totalBuyCost === null || globalCashSummary.totalBuyCost <= 0) return;
    if (globalCashSummary.totalAvailable === null || globalCashSummary.totalAvailable <= 0) return;

    const ratio = globalCashSummary.totalAvailable / globalCashSummary.totalBuyCost;
    const entries: Array<{ key: string; qty: number }> = [];

    for (const acc of kisAccounts) {
      for (const { item, suggestedQty } of buyRowsByAccount[acc.id] ?? []) {
        const key = `buy_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) continue;
        const originalQty = qtyOverrides[key] ?? suggestedQty;
        const newQty = Math.floor(originalQty * ratio);
        entries.push({ key, qty: newQty });
      }
    }

    dispatch({ type: "BULK_SET_QTY", entries });
  }

  function getAccountSummary(accountId: string) {
    const sells = (sellRowsByAccount[accountId] ?? []).filter((r) =>
      selected.has(`sell_${r.item.ticker}_${accountId}`),
    ).length;
    const buys = (buyRowsByAccount[accountId] ?? []).filter((r) =>
      selected.has(`buy_${r.item.ticker}_${accountId}`),
    ).length;
    return { sells, buys };
  }

  /* eslint-disable react-hooks/exhaustive-deps -- 마운트 시 1회만 실행 (loadAll* 포함 시 렌더마다 재조회) */
  useEffect(() => {
    void loadAllLiveBalances();
    void loadAllPrices();
  }, []);
  /* eslint-enable react-hooks/exhaustive-deps */

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
      void triggerHaptic("success");
      await invalidateSyncData(queryClient);
      onExecuted?.(res);
    } catch (e: unknown) {
      void triggerHaptic("error");
      dispatch({
        type: "EXECUTE_ERROR",
        msg: extractErrorMessage(e, "주문 실행 중 오류가 발생했습니다."),
      });
    }
  }

  function getSellRowsCached(accountId: string) {
    return sellRowsByAccount[accountId] ?? [];
  }
  function getBuyRowsCached(accountId: string) {
    return buyRowsByAccount[accountId] ?? [];
  }

  return {
    state,
    dispatch,
    kisAccounts,
    actionableItems,
    orders,
    hasRealAccount,
    getAccountQuantity,
    getSellRows: getSellRowsCached,
    getBuyRows: getBuyRowsCached,
    getBuyTotalInfo,
    getAccountSummary,
    getCashAnalysis,
    globalCashSummary,
    autoAdjustForCash,
    getLimitPriceNative,
    getEstimateKrw,
    loadLiveBalance,
    handleExecute,
  };
}

export type RebalancingExecutionHook = ReturnType<typeof useRebalancingExecution>;

export const RebalancingExecutionContext = createContext<RebalancingExecutionHook | null>(null);

export function useRebalancingExecutionContext(): RebalancingExecutionHook {
  const ctx = useContext(RebalancingExecutionContext);
  if (!ctx)
    throw new Error("useRebalancingExecutionContext must be used inside RebalancingExecutionModal");
  return ctx;
}
