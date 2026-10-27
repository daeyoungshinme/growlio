import { createContext, useContext, useEffect, useMemo, useReducer } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { AssetAccount } from "@/api/assets";
import { extractErrorMessage } from "@/utils/error";
import { invalidateRebalancingHistoryData, invalidateSyncData } from "@/utils/queryInvalidation";
import { isOrderExecutableAccount } from "@/utils/accounts";
import { triggerHaptic } from "../useHaptic";
import { isOverseasMarket } from "@/constants/markets";
import {
  type ExecutionOrderItem,
  type ExecutionResult,
  type RebalancingAnalysis,
  type RebalancingItem,
  executeRebalancing,
} from "@/api/rebalancing";
import {
  flattenTradeItems,
  getActionableItems,
  orderKey,
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
        .filter((a) => isOrderExecutableAccount(a.asset_type))
        .forEach((a) => selected.add(orderKey("sell", i.ticker, a.account_id)));
    } else if ((i.shares_to_trade ?? 0) > 0) {
      const accId = getPrimaryAccountId(i.ticker) || defaultAccId;
      if (accId) selected.add(orderKey("buy", i.ticker, accId));
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

  // 해외 잔고 조회가 실패한 계좌의 해외 종목은 실시간 잔고에 없다 — 없음(0주)으로 보면 매도 행이 사라진다
  function hasLiveBalanceFor(ticker: string, accountId: string): boolean {
    if (!liveBalances[accountId]) return false;
    if (!overseasUnknown[accountId]) return true;
    const market = flattenTradeItems(analysis.items).find((i) => i.ticker === ticker)?.market ?? "";
    return !isOverseasMarket(market);
  }

  function getAccountQuantity(ticker: string, accountId: string): number {
    const livePos = hasLiveBalanceFor(ticker, accountId)
      ? liveBalances[accountId]?.find((p) => p.ticker === ticker)
      : undefined;
    if (livePos !== undefined) return livePos.quantity;
    return (
      (analysis.ticker_account_map[ticker] ?? []).find((a) => a.account_id === accountId)
        ?.quantity ?? 0
    );
  }

  function accountHoldsTicker(ticker: string, accountId: string): boolean {
    if (hasLiveBalanceFor(ticker, accountId)) {
      return liveBalances[accountId].some((p) => p.ticker === ticker && p.quantity > 0);
    }
    return (analysis.ticker_account_map[ticker] ?? []).some(
      (a) => a.account_id === accountId && isOrderExecutableAccount(a.asset_type) && a.quantity > 0,
    );
  }

  function getLimitPriceNative(key: string, ticker: string, market: string): number {
    const raw =
      key in limitPriceOverrides
        ? limitPriceOverrides[key]
        : isOverseasMarket(market)
          ? (livePricesUsd[ticker] ?? 0)
          : (livePricesKrw[ticker] ?? 0);
    // 해외 주문 지정가는 센트 단위(소수점 2자리)까지만 허용 — Yahoo 등 원본 시세의 부동소수점 오차 제거.
    return isOverseasMarket(market) ? Math.round(raw * 100) / 100 : raw;
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
      const allKisQty = tradableAccounts.reduce(
        (sum, acc) => sum + getAccountQuantity(item.ticker, acc.id),
        0,
      );
      const totalSuggested = Math.abs(Math.round(item.shares_to_trade!));
      const suggested =
        allKisQty > 0 ? Math.round((totalSuggested * currentQty) / allKisQty) : totalSuggested;
      // 수동 계좌 등 주문 불가 계좌 보유분까지 합친 매도 권장량이 이 계좌 보유량을 넘을 수 있다
      const capped = Math.min(suggested, currentQty);
      if (capped > 0) rows.push({ item, currentQty, suggestedQty: capped });
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

  // 매수만(BUY_ONLY)이면 매도 행 자체를 만들지 않는다 — 표·현금 계산·주문 목록이 모두 이 맵을 거치므로
  // 여기서 비워야 "매수만"을 골라도 매도 주문이 나가던 문제가 한 곳에서 막힌다(plans/63 P0-1)
  const sellRowsByAccount = useMemo(() => {
    const map: Record<string, ReturnType<typeof getSellRows>> = {};
    for (const acc of tradableAccounts)
      map[acc.id] = state.strategy === "BUY_ONLY" ? [] : getSellRows(acc.id);
    return map;
    // getSellRows는 훅 스코프 함수라 dep에 넣으면 매 렌더 재계산 — 대신 그 함수가 읽는 값을 전부 나열한다
    // (getAccountQuantity·accountHoldsTicker → liveBalances·overseasUnknown·analysis)
  }, [actionableItems, liveBalances, overseasUnknown, analysis, tradableAccounts, state.strategy]); // eslint-disable-line react-hooks/exhaustive-deps

  const buyRowsByAccount = useMemo(() => {
    const map: Record<string, ReturnType<typeof getBuyRows>> = {};
    for (const acc of tradableAccounts) map[acc.id] = getBuyRows(acc.id);
    return map;
    // getBuyRows는 훅 스코프 함수 — 그 함수가 읽는 값(getAccountQuantity 경유 포함)을 전부 나열한다
  }, [actionableItems, liveBalances, overseasUnknown, analysis, buyAccounts, tradableAccounts]); // eslint-disable-line react-hooks/exhaustive-deps

  function getBuyTotalInfo(ticker: string): { allocated: number; needed: number } {
    const item = actionableItems.find((i) => i.ticker === ticker);
    const needed = Math.abs(Math.round(item?.shares_to_trade ?? 0));
    const allocated = (buyAccounts[ticker] ?? []).reduce((sum, accId) => {
      const key = orderKey("buy", ticker, accId);
      if (!selected.has(key)) return sum;
      return sum + (qtyOverrides[key] ?? needed);
    }, 0);
    return { allocated, needed };
  }

  function buildOrders(): ExecutionOrderItem[] {
    const orders: ExecutionOrderItem[] = [];
    tradableAccounts.forEach((acc) => {
      (sellRowsByAccount[acc.id] ?? []).forEach(({ item, suggestedQty, currentQty }) => {
        const key = orderKey("sell", item.ticker, acc.id);
        if (!selected.has(key)) return;
        // 보유량 초과 매도는 백엔드가 잘라 내므로, 확인 화면 수량과 실제 주문 수량이 어긋나지 않게 여기서도 자른다
        const qty = Math.min(qtyOverrides[key] ?? suggestedQty, currentQty);
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
        const key = orderKey("buy", item.ticker, acc.id);
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
      const key = orderKey("sell", item.ticker, accountId);
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
      const key = orderKey("buy", item.ticker, accountId);
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

    let totalSellProceeds: number | null = 0;
    loop: for (const acc of tradableAccounts) {
      for (const { item, suggestedQty } of sellRowsByAccount[acc.id] ?? []) {
        const key = orderKey("sell", item.ticker, acc.id);
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
    loop2: for (const acc of tradableAccounts) {
      for (const { item, suggestedQty } of buyRowsByAccount[acc.id] ?? []) {
        const key = orderKey("buy", item.ticker, acc.id);
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
    // getEstimateKrw는 훅 스코프 함수 — 실제 의존값(orderType, prices, limitPriceOverrides)은 아래에 포함됨.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tradableAccounts,
    state.balanceState,
    state.depositKrw,
    state.orderableKrw,
    sellRowsByAccount,
    buyRowsByAccount,
    selected,
    qtyOverrides,
    livePricesKrw,
    livePricesUsd,
    globalUsdRate,
    orderType,
    limitPriceOverrides,
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
