import { createContext, useContext, useEffect, useMemo, useReducer } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import { extractErrorMessage } from "@/utils/error";
import { invalidateRebalancingHistoryData, invalidateSyncData } from "@/utils/queryInvalidation";
import { isOrderExecutableAccount } from "@/utils/accounts";
import { triggerHaptic } from "../useHaptic";
import {
  type ExecutionOrderItem,
  type ExecutionResult,
  type RebalancingAnalysis,
  type RebalancingItem,
  executeRebalancing,
} from "@/api/rebalancing";
import {
  buyItemForAccount,
  canBuyInAccount,
  getActionableItems,
  orderKey,
  qtyInOriginalUnits,
} from "@/components/rebalancing/rebalancingTradeMath";
import { useRebalancingBalances } from "../useRebalancingBalances";
import { useRebalancingPrices } from "../useRebalancingPrices";
import type {
  CashAnalysis,
  GlobalCashSummary,
  OrderType,
  Phase,
  PriceLoadState,
  Strategy,
} from "./types";
import { executionReducer } from "./reducer";
import {
  buyRowItem,
  effectiveQty,
  getAccountQuantity as getAccountQuantityOf,
  getBuyRows,
  getEstimateKrw as getEstimateKrwOf,
  getLimitPriceNative as getLimitPriceNativeOf,
  getSellRows,
  referencePriceNative,
  sumSelectedEstimates,
  type PriceInput,
  type TradeRow,
  type TradeRowsInput,
} from "./rows";

export { getActionableItems };

export type {
  Phase,
  BalanceLoadState,
  OrderType,
  Strategy,
  PriceLoadState,
  CashAnalysis,
  GlobalCashSummary,
  ExecutionState,
  ExecutionAction,
} from "./types";

function computeInitialBuyAndSelected(
  analysis: RebalancingAnalysis,
  tradableAccounts: AssetAccount[],
): { buyAccounts: Record<string, string[]>; selected: Set<string> } {
  const actionableItems = getActionableItems(analysis);
  const defaultAccId = tradableAccounts[0]?.id ?? "";

  function getPrimaryAccountId(ticker: string): string {
    const infos = (analysis.ticker_account_map[ticker] ?? []).filter((a) =>
      isOrderExecutableAccount(a.asset_type),
    );
    if (infos.length === 0) return defaultAccId;
    return infos.reduce((best, a) => (a.quantity > best.quantity ? a : best)).account_id;
  }

  const taxTypeOf = (accountId: string) =>
    tradableAccounts.find((a) => a.id === accountId)?.tax_type;

  // 기본 매수 계좌가 ISA·연금인데 그 종목을 살 수 없으면(해외 상장, 국내 대체 없음) 살 수 있는 첫 계좌로 바꾼다
  function getBuyAccountId(item: RebalancingItem): string {
    const primary = getPrimaryAccountId(item.ticker);
    if (canBuyInAccount(item, analysis.items, taxTypeOf(primary))) return primary;
    return (
      tradableAccounts.find((a) => canBuyInAccount(item, analysis.items, a.tax_type))?.id ?? primary
    );
  }

  const buyAccounts: Record<string, string[]> = {};
  const selected = new Set<string>();

  if (!defaultAccId) return { buyAccounts, selected };

  actionableItems.forEach((i) => {
    if ((i.shares_to_trade ?? 0) > 0) {
      buyAccounts[i.ticker] = [getBuyAccountId(i)];
    }
  });

  actionableItems.forEach((i) => {
    if ((i.shares_to_trade ?? 0) < 0) {
      (analysis.ticker_account_map[i.ticker] ?? [])
        .filter((a) => isOrderExecutableAccount(a.asset_type))
        .forEach((a) => selected.add(orderKey("sell", i.ticker, a.account_id)));
    } else if ((i.shares_to_trade ?? 0) > 0) {
      const accId = buyAccounts[i.ticker]?.[0];
      if (!accId) return;
      // ISA·연금 계좌면 실제로 사는 종목(국내 대체)의 키로 선택해 둔다 — getBuyRows와 같은 판단
      const buyItem = buyItemForAccount(i, analysis.items, taxTypeOf(accId));
      selected.add(orderKey("buy", buyItem.ticker, accId));
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

/**
 * 지정가인데 가격이 없는 주문의 종목 — 백엔드가 LIMIT+가격 없음을 422로 거부해 배치 전체가 실패하므로
 * 실행 전에 막는다(입력을 비웠거나 해외 시세 1개만 못 받아도 생긴다).
 */
export function findMissingLimitPriceTickers(orders: ExecutionOrderItem[]): string[] {
  return orders
    .filter((o) => o.order_type === "LIMIT" && !(o.limit_price != null && o.limit_price > 0))
    .map((o) => o.ticker);
}

export function useRebalancingExecution({
  portfolioId,
  analysis,
  accounts,
  onExecuted,
}: UseRebalancingExecutionParams) {
  const queryClient = useQueryClient();
  // 아래 useMemo 여러 곳의 의존성이라 매 렌더 새 배열이면 메모가 전부 무력화된다(plans/62 B7)
  const tradableAccounts = useMemo(
    () => accounts.filter((a) => isOrderExecutableAccount(a.asset_type)),
    [accounts],
  );

  const [state, dispatch] = useReducer(
    executionReducer,
    { analysis, tradableAccounts },
    ({ analysis: a, tradableAccounts: kas }) => {
      const { buyAccounts, selected } = computeInitialBuyAndSelected(a, kas);
      return {
        liveBalances: {},
        overseasUnknown: {},
        balanceState: {},
        depositKrw: {},
        orderableKrw: {},
        priceState: "idle" as PriceLoadState,
        priceLoadProgress: { loaded: 0, total: 0 },
        livePricesKrw: {},
        livePricesUsd: {},
        priceRetrying: new Set<string>(),
        globalUsdRate: null,
        orderType: "MARKET" as OrderType,
        strategy: "FULL" as Strategy,
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
    overseasUnknown,
    qtyOverrides,
    buyAccounts,
    selected,
    orderType,
    limitPriceOverrides,
    livePricesKrw,
    livePricesUsd,
    globalUsdRate,
  } = state;

  const actionableItems = useMemo(() => getActionableItems(analysis), [analysis]);
  const { loadLiveBalance, loadAllLiveBalances } = useRebalancingBalances(
    dispatch,
    tradableAccounts,
  );
  const { loadAllPrices, retryPrice } = useRebalancingPrices(dispatch, analysis);

  const prices: PriceInput = useMemo(
    () => ({ orderType, limitPriceOverrides, livePricesKrw, livePricesUsd, globalUsdRate }),
    [orderType, limitPriceOverrides, livePricesKrw, livePricesUsd, globalUsdRate],
  );
  const rowsInput: TradeRowsInput = useMemo(
    () => ({ analysis, liveBalances, overseasUnknown, actionableItems, tradableAccounts }),
    [analysis, liveBalances, overseasUnknown, actionableItems, tradableAccounts],
  );

  // 매수만(BUY_ONLY)이면 매도 행 자체를 만들지 않는다 — 표·현금 계산·주문 목록이 모두 이 맵을 거치므로
  // 여기서 비워야 "매수만"을 골라도 매도 주문이 나가던 문제가 한 곳에서 막힌다(plans/63 P0-1)
  const sellRowsByAccount = useMemo(() => {
    const map: Record<string, TradeRow[]> = {};
    for (const acc of tradableAccounts)
      map[acc.id] = state.strategy === "BUY_ONLY" ? [] : getSellRows(rowsInput, acc.id);
    return map;
  }, [rowsInput, tradableAccounts, state.strategy]);

  const buyRowsByAccount = useMemo(() => {
    const map: Record<string, TradeRow[]> = {};
    for (const acc of tradableAccounts) map[acc.id] = getBuyRows(rowsInput, buyAccounts, acc.id);
    return map;
  }, [rowsInput, tradableAccounts, buyAccounts]);

  /** 여러 계좌에 나눠 사는 종목의 배분 합계 — 국내 대체 행 수량은 원래 종목 주수로 환산해 더한다. */
  function getBuyTotalInfo(ticker: string): { allocated: number; needed: number } {
    const item = actionableItems.find((i) => i.ticker === ticker);
    const needed = Math.abs(Math.round(item?.shares_to_trade ?? 0));
    if (!item) return { allocated: 0, needed };
    const allocated = (buyAccounts[ticker] ?? []).reduce((sum, accId) => {
      const row = buyRowItem(analysis, tradableAccounts, item, accId);
      const key = orderKey("buy", row.ticker, accId);
      if (!selected.has(key)) return sum;
      const qty = qtyOverrides[key] ?? Math.abs(Math.round(row.shares_to_trade ?? 0));
      return sum + qtyInOriginalUnits(row, item, qty);
    }, 0);
    return { allocated, needed };
  }

  /** "이 계좌에 매수 종목 추가" 후보 — 아직 이 계좌에 배정되지 않았고 이 계좌에서 살 수 있는 종목(plans/80 A2). */
  function getAddableBuyItems(accountId: string): RebalancingItem[] {
    const taxType = tradableAccounts.find((a) => a.id === accountId)?.tax_type;
    return actionableItems.filter(
      (i) =>
        (i.shares_to_trade ?? 0) > 0 &&
        !(buyAccounts[i.ticker] ?? []).includes(accountId) &&
        canBuyInAccount(i, analysis.items, taxType),
    );
  }

  function addBuyAccount(ticker: string, accountId: string) {
    const item = actionableItems.find((i) => i.ticker === ticker);
    const rowTicker = item
      ? buyRowItem(analysis, tradableAccounts, item, accountId).ticker
      : ticker;
    dispatch({ type: "ADD_BUY_ACCOUNT", ticker, accountId, rowTicker });
  }

  function buildOrders(): ExecutionOrderItem[] {
    const orders: ExecutionOrderItem[] = [];
    tradableAccounts.forEach((acc) => {
      (sellRowsByAccount[acc.id] ?? []).forEach((row) => {
        const { item } = row;
        const key = orderKey("sell", item.ticker, acc.id);
        if (!selected.has(key)) return;
        const qty = effectiveQty("sell", row, qtyOverrides[key]);
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
                ? getLimitPriceNativeOf(prices, key, item.ticker, item.market) || null
                : null,
            reference_price: referencePriceNative(prices, item.ticker, item.market),
          });
      });
      (buyRowsByAccount[acc.id] ?? []).forEach((row) => {
        const { item } = row;
        const key = orderKey("buy", item.ticker, acc.id);
        if (!selected.has(key)) return;
        const qty = effectiveQty("buy", row, qtyOverrides[key]);
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
                ? getLimitPriceNativeOf(prices, key, item.ticker, item.market) || null
                : null,
            reference_price: referencePriceNative(prices, item.ticker, item.market),
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
    const sellProceeds = sumSelectedEstimates(
      prices,
      sellRowsByAccount[accountId] ?? [],
      "sell",
      accountId,
      selected,
      qtyOverrides,
    );
    const buyCost = sumSelectedEstimates(
      prices,
      buyRowsByAccount[accountId] ?? [],
      "buy",
      accountId,
      selected,
      qtyOverrides,
    );
    const totalAvailable =
      deposit !== null && sellProceeds !== null ? deposit + sellProceeds : null;
    const surplus = totalAvailable !== null && buyCost !== null ? totalAvailable - buyCost : null;
    return { deposit, isOrderableKnown, sellProceeds, totalAvailable, buyCost, surplus };
  }

  const globalCashSummary = useMemo((): GlobalCashSummary => {
    const balancesLoaded = tradableAccounts.some((acc) => state.balanceState[acc.id] === "loaded");
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
    for (const acc of tradableAccounts) {
      const useOrderable = acc.id in state.orderableKrw;
      totalDeposit += useOrderable
        ? (state.orderableKrw[acc.id] ?? 0)
        : (state.depositKrw[acc.id] ?? 0);
    }

    // 계좌별 합 — 한 계좌라도 시세를 모르면 전체도 모름(null)
    const sumAll = (byAccount: Record<string, TradeRow[]>, side: "sell" | "buy") => {
      let total = 0;
      for (const acc of tradableAccounts) {
        const sub = sumSelectedEstimates(
          prices,
          byAccount[acc.id] ?? [],
          side,
          acc.id,
          selected,
          qtyOverrides,
        );
        if (sub === null) return null;
        total += sub;
      }
      return total;
    };
    const totalSellProceeds = sumAll(sellRowsByAccount, "sell");
    const totalBuyCost = sumAll(buyRowsByAccount, "buy");

    const totalAvailable = totalSellProceeds !== null ? totalDeposit + totalSellProceeds : null;
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
  }, [
    tradableAccounts,
    state.balanceState,
    state.depositKrw,
    state.orderableKrw,
    sellRowsByAccount,
    buyRowsByAccount,
    selected,
    qtyOverrides,
    prices,
  ]);

  function autoAdjustForCash() {
    if (!globalCashSummary.balancesLoaded || !globalCashSummary.isInsufficient) return;
    if (globalCashSummary.totalBuyCost === null || globalCashSummary.totalBuyCost <= 0) return;
    if (globalCashSummary.totalAvailable === null || globalCashSummary.totalAvailable <= 0) return;

    const ratio = globalCashSummary.totalAvailable / globalCashSummary.totalBuyCost;
    const entries: Array<{ key: string; qty: number }> = [];

    for (const acc of tradableAccounts) {
      for (const { item, suggestedQty } of buyRowsByAccount[acc.id] ?? []) {
        const key = orderKey("buy", item.ticker, acc.id);
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
      selected.has(orderKey("sell", r.item.ticker, accountId)),
    ).length;
    const buys = (buyRowsByAccount[accountId] ?? []).filter((r) =>
      selected.has(orderKey("buy", r.item.ticker, accountId)),
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
    const acc = tradableAccounts.find((a) => a.id === o.account_id);
    return acc && !acc.is_mock_mode;
  });

  const missingLimitPriceTickers = findMissingLimitPriceTickers(orders);

  async function handleExecute() {
    if (orders.length === 0 || missingLimitPriceTickers.length > 0) return;
    dispatch({ type: "EXECUTE_START" });
    try {
      const res = await executeRebalancing(portfolioId, {
        account_id: null,
        orders,
        strategy: state.strategy,
      });
      dispatch({ type: "EXECUTE_SUCCESS", results: res });
      void triggerHaptic("success");
      await Promise.all([
        invalidateSyncData(queryClient),
        invalidateRebalancingHistoryData(queryClient),
      ]);
      onExecuted?.(res);
    } catch (e: unknown) {
      void triggerHaptic("error");
      dispatch({
        type: "EXECUTE_ERROR",
        msg: extractErrorMessage(e, "주문 실행 중 오류가 발생했습니다."),
      });
    }
  }

  // 컴포넌트가 쓰는 기존 시그니처 유지
  const getAccountQuantity = (ticker: string, accountId: string) =>
    getAccountQuantityOf(rowsInput, ticker, accountId);
  const getLimitPriceNative = (key: string, ticker: string, market: string) =>
    getLimitPriceNativeOf(prices, key, ticker, market);
  const getEstimateKrw = (key: string, ticker: string, market: string, qty: number) =>
    getEstimateKrwOf(prices, key, ticker, market, qty);

  function getSellRowsCached(accountId: string) {
    return sellRowsByAccount[accountId] ?? [];
  }
  function getBuyRowsCached(accountId: string) {
    return buyRowsByAccount[accountId] ?? [];
  }

  return {
    state,
    dispatch,
    tradableAccounts,
    actionableItems,
    orders,
    missingLimitPriceTickers,
    hasRealAccount,
    getAccountQuantity,
    getSellRows: getSellRowsCached,
    getBuyRows: getBuyRowsCached,
    getBuyTotalInfo,
    getAddableBuyItems,
    addBuyAccount,
    getAccountSummary,
    getCashAnalysis,
    globalCashSummary,
    autoAdjustForCash,
    getLimitPriceNative,
    getEstimateKrw,
    loadLiveBalance,
    loadAllPrices,
    retryPrice,
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
