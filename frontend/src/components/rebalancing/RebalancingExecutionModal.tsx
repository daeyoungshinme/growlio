import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AssetAccount } from "../../api/assets";
import {
  ExecutionOrderItem,
  ExecutionResult,
  KisBalancePosition,
  KisBalanceResponse,
  OrderResult,
  RebalancingAnalysis,
  RebalancingItem,
  TickerAccountInfo,
  executeRebalancing,
  fetchAllKisBalances,
  fetchAllKiwoomBalances,
  fetchKisBalance,
  fetchKiwoomBalance,
  fetchStockPrice,
} from "../../api/rebalancing";
import { fmtKrw } from "../../utils/format";

interface Props {
  portfolioId: string;
  analysis: RebalancingAnalysis;
  accounts: AssetAccount[];
  onExecuted?: (results: ExecutionResult[]) => void;
  onClose: () => void;
}

type Phase = "confirm" | "executing" | "result";
type BalanceLoadState = "idle" | "loading" | "loaded" | "error" | "not_found";
type OrderType = "MARKET" | "LIMIT";
type PriceLoadState = "idle" | "loading" | "loaded" | "error";

const OVERSEAS_MARKET_SET = new Set(["NYSE", "NASDAQ", "AMEX", "NYSE_US", "NASDAQ_US", "AMEX_US"]);
function isOverseasMarket(market: string): boolean {
  return OVERSEAS_MARKET_SET.has(market.toUpperCase());
}

function getActionableItems(analysis: RebalancingAnalysis): RebalancingItem[] {
  return analysis.items.filter(
    (i) =>
      i.ticker !== "CASH" &&
      i.market !== "KR_PROPERTY" &&
      i.shares_to_trade !== null &&
      Math.abs(i.shares_to_trade) >= 1
  );
}

function SideBadge({ isBuy }: { isBuy: boolean }) {
  return (
    <span className={`font-medium text-xs ${isBuy ? "text-red-400" : "text-blue-400"}`}>
      {isBuy ? "매수" : "매도"}
    </span>
  );
}

function StatusBadge({ status }: { status: OrderResult["status"] }) {
  if (status === "SUCCESS")
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-900/30 text-green-400">
        성공
      </span>
    );
  if (status === "FAILED")
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-900/30 text-red-400">
        실패
      </span>
    );
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-700 text-gray-400">
      건너뜀
    </span>
  );
}

export function RebalancingExecutionModal({ portfolioId, analysis, accounts, onExecuted, onClose }: Props) {
  const queryClient = useQueryClient();
  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM");

  // 실시간 잔고
  const [liveBalances, setLiveBalances] = useState<Record<string, KisBalancePosition[]>>({});
  const [balanceState, setBalanceState] = useState<Record<string, BalanceLoadState>>({});
  const [depositKrw, setDepositKrw] = useState<Record<string, number>>({});

  // 현재가 (ticker → 가격)
  const [priceState, setPriceState] = useState<PriceLoadState>("idle");
  const [livePricesKrw, setLivePricesKrw] = useState<Record<string, number>>({});
  const [livePricesUsd, setLivePricesUsd] = useState<Record<string, number>>({});
  const [globalUsdRate, setGlobalUsdRate] = useState<number | null>(null);

  // 주문 유형 + 지정가 오버라이드
  const [orderType, setOrderType] = useState<OrderType>("MARKET");
  // 국내=KRW, 해외=USD 단위로 저장
  const [limitPriceOverrides, setLimitPriceOverrides] = useState<Record<string, number>>({});

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
      (a) => a.account_id === accountId && (a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM") && a.quantity > 0
    );
  }

  async function loadLiveBalance(accountId: string) {
    setBalanceState((prev) => ({ ...prev, [accountId]: "loading" }));
    try {
      const acc = kisAccounts.find((a) => a.id === accountId);
      const fetchFn = acc?.asset_type === "STOCK_KIWOOM" ? fetchKiwoomBalance : fetchKisBalance;
      const res: KisBalanceResponse = await fetchFn(accountId);
      setLiveBalances((prev) => ({ ...prev, [accountId]: res.positions }));
      setDepositKrw((prev) => ({ ...prev, [accountId]: res.deposit_krw }));
      setBalanceState((prev) => ({ ...prev, [accountId]: "loaded" }));
    } catch (err: unknown) {
      const httpStatus = (err as { response?: { status?: number } }).response?.status;
      if (httpStatus === 404) {
        setBalanceState((prev) => ({ ...prev, [accountId]: "not_found" }));
        queryClient.invalidateQueries({ queryKey: ["accounts"] });
      } else {
        setBalanceState((prev) => ({ ...prev, [accountId]: "error" }));
      }
    }
  }

  async function loadAllLiveBalances() {
    if (kisAccounts.length === 0) return;
    const loadingState: Record<string, BalanceLoadState> = {};
    kisAccounts.forEach((acc) => { loadingState[acc.id] = "loading"; });
    setBalanceState(loadingState);

    try {
      const kisOnly = kisAccounts.filter((a) => a.asset_type === "STOCK_KIS");
      const kiwoomOnly = kisAccounts.filter((a) => a.asset_type === "STOCK_KIWOOM");

      const [kisResponses, kiwoomResponses] = await Promise.all([
        kisOnly.length > 0 ? fetchAllKisBalances() : Promise.resolve([]),
        kiwoomOnly.length > 0 ? fetchAllKiwoomBalances() : Promise.resolve([]),
      ]);

      const responses: KisBalanceResponse[] = [...kisResponses, ...kiwoomResponses];
      const newBalances: Record<string, KisBalancePosition[]> = {};
      const newDeposits: Record<string, number> = {};
      const newStates: Record<string, BalanceLoadState> = {};

      responses.forEach((res) => {
        if (res.error) {
          newStates[res.account_id] = "error";
        } else {
          newBalances[res.account_id] = res.positions;
          newDeposits[res.account_id] = res.deposit_krw;
          newStates[res.account_id] = "loaded";
        }
      });

      setLiveBalances(newBalances);
      setDepositKrw(newDeposits);
      setBalanceState((prev) => ({ ...prev, ...newStates }));
    } catch {
      const errState: Record<string, BalanceLoadState> = {};
      kisAccounts.forEach((acc) => { errState[acc.id] = "error"; });
      setBalanceState(errState);
    }
  }

  async function loadAllPrices() {
    const actionableItems = getActionableItems(analysis);
    const tickerMarketMap = new Map<string, string>();
    actionableItems.forEach((i) => {
      if (i.ticker !== "CASH") tickerMarketMap.set(i.ticker, i.market);
    });
    analysis.untracked_holdings.forEach((h) => tickerMarketMap.set(h.ticker, h.market));

    if (tickerMarketMap.size === 0) return;
    setPriceState("loading");

    const entries = Array.from(tickerMarketMap.entries());
    const results = await Promise.allSettled(
      entries.map(([ticker, market]) => fetchStockPrice(ticker, market))
    );

    const newKrw: Record<string, number> = {};
    const newUsd: Record<string, number> = {};
    let latestUsdRate: number | null = null;

    results.forEach((result, idx) => {
      const [ticker] = entries[idx];
      if (result.status === "fulfilled") {
        const { price_krw, price_usd, usd_rate } = result.value;
        if (price_krw != null) newKrw[ticker] = price_krw;
        if (price_usd != null) newUsd[ticker] = price_usd;
        if (usd_rate != null) latestUsdRate = usd_rate;
      }
    });

    setLivePricesKrw(newKrw);
    setLivePricesUsd(newUsd);
    if (latestUsdRate != null) setGlobalUsdRate(latestUsdRate);
    setPriceState(Object.keys(newKrw).length > 0 ? "loaded" : "error");
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    loadAllLiveBalances();
    loadAllPrices();
  }, []);

  function getKisInfos(ticker: string): TickerAccountInfo[] {
    return (analysis.ticker_account_map[ticker] ?? []).filter(
      (a) => a.asset_type === "STOCK_KIS"
    );
  }

  function primaryKisAccountId(ticker: string): string {
    const defaultId = kisAccounts[0]?.id ?? "";
    const infos = getKisInfos(ticker);
    if (infos.length === 0) return defaultId;
    return infos.reduce((best, a) => (a.quantity > best.quantity ? a : best), infos[0]).account_id;
  }

  const actionableItems = getActionableItems(analysis);

  const [qtyOverrides, setQtyOverrides] = useState<Record<string, number>>({});

  const [buyAccounts, setBuyAccounts] = useState<Record<string, string[]>>(() => {
    const defaultAccId = kisAccounts[0]?.id ?? "";
    const map: Record<string, string[]> = {};
    if (!defaultAccId) return map;
    actionableItems.forEach((i) => {
      if ((i.shares_to_trade ?? 0) > 0)
        map[i.ticker] = [primaryKisAccountId(i.ticker)];
    });
    return map;
  });

  const [selected, setSelected] = useState<Set<string>>(() => {
    const keys = new Set<string>();
    const defaultAccId = kisAccounts[0]?.id ?? "";
    actionableItems.forEach((i) => {
      if ((i.shares_to_trade ?? 0) < 0) {
        getKisInfos(i.ticker).forEach((a) => keys.add(`sell_${i.ticker}_${a.account_id}`));
      } else if ((i.shares_to_trade ?? 0) > 0) {
        const accId = primaryKisAccountId(i.ticker) || defaultAccId;
        if (accId) keys.add(`buy_${i.ticker}_${accId}`);
      }
    });
    return keys;
  });

  const [phase, setPhase] = useState<Phase>("confirm");
  const [results, setResults] = useState<ExecutionResult[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // 지정가의 native 가격 (국내=KRW, 해외=USD) — override 없으면 실시간 가격 반환
  function getLimitPriceNative(key: string, ticker: string, market: string): number {
    if (key in limitPriceOverrides) return limitPriceOverrides[key];
    return isOverseasMarket(market)
      ? (livePricesUsd[ticker] ?? 0)
      : (livePricesKrw[ticker] ?? 0);
  }

  function setLimitPrice(key: string, val: number) {
    setLimitPriceOverrides((prev) => ({ ...prev, [key]: Math.max(0, val) }));
  }

  // 예상 체결금액 (KRW 기준)
  function getEstimateKrw(key: string, ticker: string, market: string, qty: number): number | null {
    if (orderType === "LIMIT") {
      const native = getLimitPriceNative(key, ticker, market);
      if (native <= 0) return null;
      if (isOverseasMarket(market)) {
        return globalUsdRate != null ? native * globalUsdRate * qty : null;
      }
      return native * qty;
    }
    const priceKrw = livePricesKrw[ticker] ?? null;
    return priceKrw != null ? priceKrw * qty : null;
  }

  function getSellRows(accountId: string): {
    item: RebalancingItem;
    currentQty: number;
    suggestedQty: number;
  }[] {
    const rows: { item: RebalancingItem; currentQty: number; suggestedQty: number }[] = [];

    for (const item of actionableItems) {
      if ((item.shares_to_trade ?? 0) >= 0) continue;
      if (!accountHoldsTicker(item.ticker, accountId)) continue;

      const currentQty = getAccountQuantity(item.ticker, accountId);
      if (currentQty <= 0) continue;

      const allKisQty = kisAccounts.reduce(
        (sum, acc) => sum + getAccountQuantity(item.ticker, acc.id),
        0
      );
      const suggested =
        allKisQty > 0
          ? Math.round(Math.abs(item.shares_to_trade!) * currentQty / allKisQty)
          : Math.abs(Math.round(item.shares_to_trade!));
      if (suggested > 0) {
        rows.push({ item, currentQty, suggestedQty: suggested });
      }
    }
    return rows;
  }

  function getBuyRows(accountId: string): {
    item: RebalancingItem;
    suggestedQty: number;
    currentQty: number;
  }[] {
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

  const orders = buildOrders();

  const hasRealAccount = orders.some((o) => {
    const acc = kisAccounts.find((a) => a.id === o.account_id);
    return acc && !acc.is_mock_mode;
  });

  function toggleKey(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function setQty(key: string, val: number) {
    setQtyOverrides((prev) => ({ ...prev, [key]: Math.max(0, val) }));
  }

  function addBuyAccount(ticker: string, accountId: string) {
    setBuyAccounts((prev) => ({ ...prev, [ticker]: [...(prev[ticker] ?? []), accountId] }));
    setQtyOverrides((prev) => ({ ...prev, [`buy_${ticker}_${accountId}`]: 0 }));
  }

  function removeBuyAccount(ticker: string, accountId: string) {
    setBuyAccounts((prev) => ({ ...prev, [ticker]: (prev[ticker] ?? []).filter((id) => id !== accountId) }));
    const key = `buy_${ticker}_${accountId}`;
    setSelected((prev) => { const next = new Set(prev); next.delete(key); return next; });
    setQtyOverrides((prev) => { const next = { ...prev }; delete next[key]; return next; });
  }

  async function handleExecute() {
    if (orders.length === 0) return;
    setPhase("executing");
    setErrorMsg(null);
    try {
      const res = await executeRebalancing(portfolioId, { account_id: null, orders });
      setResults(res);
      setPhase("result");
      onExecuted?.(res);
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : "주문 실행 중 오류가 발생했습니다.");
      setPhase("confirm");
    }
  }

  function getAccountSummary(accountId: string) {
    const sells = getSellRows(accountId).filter((r) => selected.has(`sell_${r.item.ticker}_${accountId}`)).length;
    const buys = getBuyRows(accountId).filter((r) => selected.has(`buy_${r.item.ticker}_${accountId}`)).length;
    return { sells, buys };
  }

  // 현재가 셀 렌더링 헬퍼
  function renderPriceCell(ticker: string, market: string) {
    const krw = livePricesKrw[ticker];
    const usd = livePricesUsd[ticker];
    if (priceState === "loading") {
      return <span className="text-gray-600 text-[11px]">조회 중</span>;
    }
    if (krw != null) {
      if (isOverseasMarket(market) && usd != null) {
        return (
          <div>
            <div className="text-gray-300 text-[11px]">${usd.toFixed(2)}</div>
            <div className="text-gray-500 text-[11px]">≈ {fmtKrw(krw)}</div>
          </div>
        );
      }
      return <span className="text-gray-300 text-[11px]">{fmtKrw(krw)}</span>;
    }
    return <span className="text-gray-600 text-[11px]">—</span>;
  }

  // 지정가 입력 셀 렌더링 헬퍼
  function renderLimitPriceCell(key: string, ticker: string, market: string, qty: number) {
    if (orderType !== "LIMIT") return <td />;
    const overseas = isOverseasMarket(market);
    const nativeVal = getLimitPriceNative(key, ticker, market);
    const estKrw = overseas && globalUsdRate != null ? nativeVal * globalUsdRate * qty : nativeVal * qty;

    return (
      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-1">
          <input
            type="number"
            min={0}
            step={overseas ? 0.01 : 1}
            value={nativeVal || ""}
            placeholder={overseas ? "USD" : "KRW"}
            onChange={(e) => setLimitPrice(key, parseFloat(e.target.value) || 0)}
            className="w-20 bg-gray-800 border border-indigo-600/50 rounded px-2 py-0.5 text-right text-indigo-300 font-medium text-[11px] focus:outline-none focus:border-indigo-500"
          />
          <span className="text-gray-500 text-[11px]">{overseas ? "USD" : "원"}</span>
        </div>
        {nativeVal > 0 && (
          <div className="text-[11px] text-gray-600 mt-0.5 text-right">
            ≈ {fmtKrw(overseas && globalUsdRate != null ? nativeVal * globalUsdRate : nativeVal)} × {qty}주 = {fmtKrw(estKrw)}
          </div>
        )}
      </td>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-white">리밸런싱 실행</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors text-xl leading-none">
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">

          {/* ── 확인 단계 ── */}
          {phase === "confirm" && (
            <>
              <div className="rounded-lg bg-yellow-900/30 border border-yellow-700/50 px-4 py-3 text-xs text-yellow-300">
                주문이 즉시 체결됩니다. 내용을 신중히 확인하세요.
              </div>

              {hasRealAccount && (
                <div className="rounded-lg bg-red-900/30 border border-red-700/50 px-4 py-3 text-xs text-red-300 font-medium">
                  실계좌 주문입니다. 실제 자금이 사용됩니다.
                </div>
              )}

              <div className="text-xs text-gray-500">
                시장이 닫혀 있을 경우 주문이 예약될 수 있습니다.
              </div>

              {/* 주문 유형 토글 */}
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-400">주문 유형</span>
                <div className="flex rounded-lg border border-gray-700 overflow-hidden">
                  <button
                    onClick={() => setOrderType("MARKET")}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      orderType === "MARKET"
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:text-white"
                    }`}
                  >
                    시장가
                  </button>
                  <button
                    onClick={() => setOrderType("LIMIT")}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      orderType === "LIMIT"
                        ? "bg-indigo-600 text-white"
                        : "bg-gray-800 text-gray-400 hover:text-white"
                    }`}
                  >
                    지정가
                  </button>
                </div>
                {priceState === "loading" && (
                  <span className="text-xs text-gray-500">현재가 조회 중...</span>
                )}
                {priceState === "error" && (
                  <span className="text-xs text-amber-400">현재가 조회 실패 — 지정가 직접 입력 가능</span>
                )}
              </div>

              {errorMsg && (
                <div className="rounded-lg bg-red-900/30 border border-red-700/50 px-4 py-3 text-xs text-red-300">
                  {errorMsg}
                </div>
              )}

              {kisAccounts.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">연결된 KIS/키움 계좌가 없습니다.</p>
              ) : (
                <>
                  {kisAccounts.map((acc) => {
                    const sellRows = getSellRows(acc.id);
                    const buyRows = getBuyRows(acc.id);
                    const bState = balanceState[acc.id] ?? "idle";
                    const unassignedBuyItems = actionableItems.filter(
                      (i) => (i.shares_to_trade ?? 0) > 0 && !(buyAccounts[i.ticker] ?? []).includes(acc.id)
                    );
                    const hasData = sellRows.length > 0 || buyRows.length > 0 || unassignedBuyItems.length > 0;

                    const { sells, buys } = getAccountSummary(acc.id);

                    return (
                      <div key={acc.id} className="border border-gray-700 rounded-xl overflow-hidden">
                        {/* 계좌 헤더 */}
                        <div className="bg-gray-800/70 px-4 py-2.5 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-white">{acc.name}</span>
                            {acc.kis_account_no && (
                              <span className="text-xs text-gray-400">({acc.kis_account_no})</span>
                            )}
                            <span
                              className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
                                acc.is_mock_mode
                                  ? "bg-yellow-900/40 text-yellow-400 border border-yellow-700/50"
                                  : "bg-red-900/30 text-red-400 border border-red-700/40"
                              }`}
                            >
                              {acc.is_mock_mode ? "모의" : "실계좌"}
                            </span>
                            {!acc.is_active && (
                              <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400 border border-gray-600">
                                비활성
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-gray-400">
                              {sells > 0 && <span className="text-blue-400">매도 {sells}건</span>}
                              {sells > 0 && buys > 0 && <span className="text-gray-600 mx-1">|</span>}
                              {buys > 0 && <span className="text-red-400">매수 {buys}건</span>}
                            </span>
                            {depositKrw[acc.id] != null && (
                              <span className="text-[11px] text-gray-500">
                                예수금 <span className="text-gray-300">{fmtKrw(depositKrw[acc.id])}</span>
                              </span>
                            )}
                            <button
                              onClick={() => loadLiveBalance(acc.id)}
                              disabled={bState === "loading"}
                              className="text-[11px] px-2 py-0.5 rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50 transition-colors border border-gray-600"
                            >
                              {bState === "loading" ? "조회 중..." : bState === "loaded" ? "✓ 잔고 반영" : bState === "not_found" ? "계좌 없음" : bState === "error" ? "오류 (재시도)" : "잔고 조회"}
                            </button>
                          </div>
                        </div>

                        {!hasData && bState !== "loaded" && (
                          <div className="px-4 py-3 text-xs text-gray-500 text-center">
                            분석 결과에 보유 종목이 없습니다. 잔고 조회로 실시간 보유 종목을 불러오세요.
                          </div>
                        )}

                        {hasData && (
                          <div>
                            {(sellRows.length > 0 || buyRows.length > 0) && (
                              <div className="overflow-x-auto">
                                <table className="w-full text-xs">
                                  <colgroup>
                                    <col style={{ width: '32px' }} />
                                    <col />
                                    <col style={{ width: '56px' }} />
                                    <col style={{ width: '110px' }} />
                                    <col style={{ width: '140px' }} />
                                    {orderType === "LIMIT" && <col style={{ width: '176px' }} />}
                                    <col style={{ width: '32px' }} />
                                  </colgroup>
                                  <thead>
                                    <tr className="text-[11px] text-gray-500 border-b border-gray-700/50">
                                      <th />
                                      <th className="px-3 py-2 text-left font-normal">종목</th>
                                      <th className="px-3 py-2 text-center font-normal">구분</th>
                                      <th className="px-2 py-2 text-right font-normal">현재가</th>
                                      <th className="px-3 py-2 text-right font-normal">수량</th>
                                      {orderType === "LIMIT" && <th className="px-2 py-2 text-right font-normal">지정가</th>}
                                      <th />
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-gray-700/30">
                                    {/* 매도 섹션 */}
                                    {sellRows.length > 0 && (
                                      <>
                                        <tr>
                                          <td
                                            colSpan={orderType === "LIMIT" ? 7 : 6}
                                            className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30"
                                          >
                                            매도
                                          </td>
                                        </tr>
                                        {sellRows.map(({ item, currentQty, suggestedQty }) => {
                                          const key = `sell_${item.ticker}_${acc.id}`;
                                          const qty = qtyOverrides[key] ?? suggestedQty;
                                          const est = getEstimateKrw(key, item.ticker, item.market, qty);
                                          return (
                                            <tr key={key} className="hover:bg-gray-800/40 cursor-pointer" onClick={() => toggleKey(key)}>
                                              <td className="px-3 py-2">
                                                <input
                                                  type="checkbox"
                                                  checked={selected.has(key)}
                                                  onChange={() => toggleKey(key)}
                                                  onClick={(e) => e.stopPropagation()}
                                                  className="accent-indigo-500"
                                                />
                                              </td>
                                              <td className="px-3 py-2">
                                                <div className="text-white font-medium truncate max-w-[120px]">{item.name}</div>
                                                <div className="text-gray-400 text-[11px]">{item.ticker}</div>
                                                <div className="text-gray-500 text-[11px]">현재 {currentQty.toLocaleString()}주 보유</div>
                                              </td>
                                              <td className="px-3 py-2 text-center">
                                                <SideBadge isBuy={false} />
                                              </td>
                                              <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                                {renderPriceCell(item.ticker, item.market)}
                                              </td>
                                              <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                                <div className="flex items-center justify-end gap-1">
                                                  <input
                                                    type="number"
                                                    min={0}
                                                    value={qty}
                                                    onChange={(e) => setQty(key, parseInt(e.target.value) || 0)}
                                                    className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-blue-400 font-medium focus:outline-none focus:border-indigo-500"
                                                  />
                                                  <span className="text-gray-400">주</span>
                                                </div>
                                                {est != null && orderType === "MARKET" && (
                                                  <div className="text-[11px] text-gray-500 mt-0.5 text-right">≈ {fmtKrw(est)}</div>
                                                )}
                                              </td>
                                              {renderLimitPriceCell(key, item.ticker, item.market, qty)}
                                              <td />
                                            </tr>
                                          );
                                        })}
                                      </>
                                    )}

                                    {/* 매수 섹션 */}
                                    {buyRows.length > 0 && (
                                      <>
                                        <tr>
                                          <td
                                            colSpan={orderType === "LIMIT" ? 7 : 6}
                                            className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30"
                                          >
                                            매수
                                          </td>
                                        </tr>
                                        {buyRows.map(({ item, suggestedQty, currentQty }) => {
                                          const key = `buy_${item.ticker}_${acc.id}`;
                                          const qty = qtyOverrides[key] ?? suggestedQty;
                                          const est = getEstimateKrw(key, item.ticker, item.market, qty);
                                          const isMultiAccount = (buyAccounts[item.ticker] ?? []).length > 1;
                                          const isOnlyAccount = !isMultiAccount;
                                          const { allocated, needed } = isMultiAccount ? getBuyTotalInfo(item.ticker) : { allocated: 0, needed: 0 };
                                          return (
                                            <tr key={key} className="hover:bg-gray-800/40 cursor-pointer" onClick={() => toggleKey(key)}>
                                              <td className="px-3 py-2">
                                                <input
                                                  type="checkbox"
                                                  checked={selected.has(key)}
                                                  onChange={() => toggleKey(key)}
                                                  onClick={(e) => e.stopPropagation()}
                                                  className="accent-indigo-500"
                                                />
                                              </td>
                                              <td className="px-3 py-2">
                                                <div className="text-white font-medium truncate max-w-[120px]">{item.name}</div>
                                                <div className="text-gray-400 text-[11px]">{item.ticker}</div>
                                                <div className="text-gray-500 text-[11px]">
                                                  {currentQty > 0 ? `현재 ${currentQty.toLocaleString()}주 보유` : "현재 미보유"}
                                                </div>
                                              </td>
                                              <td className="px-3 py-2 text-center">
                                                <SideBadge isBuy={true} />
                                              </td>
                                              <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                                {renderPriceCell(item.ticker, item.market)}
                                              </td>
                                              <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                                <div className="flex items-center justify-end gap-1">
                                                  <input
                                                    type="number"
                                                    min={0}
                                                    value={qty}
                                                    onChange={(e) => {
                                                      const val = parseInt(e.target.value) || 0;
                                                      setQtyOverrides((prev) => ({ ...prev, [key]: Math.max(0, val) }));
                                                      if (val > 0) setSelected((prev) => new Set([...prev, key]));
                                                      else setSelected((prev) => { const next = new Set(prev); next.delete(key); return next; });
                                                    }}
                                                    className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-red-400 font-medium focus:outline-none focus:border-indigo-500"
                                                  />
                                                  <span className="text-gray-400">주</span>
                                                </div>
                                                {isMultiAccount ? (
                                                  <div className={`text-[11px] mt-0.5 text-right ${allocated === needed ? "text-gray-500" : "text-amber-400"}`}>
                                                    배분 {allocated} / {needed}주
                                                  </div>
                                                ) : (
                                                  est != null && orderType === "MARKET" && (
                                                    <div className="text-[11px] text-gray-500 mt-0.5 text-right">≈ {fmtKrw(est)}</div>
                                                  )
                                                )}
                                              </td>
                                              {renderLimitPriceCell(key, item.ticker, item.market, qty)}
                                              <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                                <button
                                                  onClick={() => removeBuyAccount(item.ticker, acc.id)}
                                                  disabled={isOnlyAccount}
                                                  title="이 계좌에서 제거"
                                                  className="text-gray-600 hover:text-red-400 disabled:opacity-20 disabled:cursor-not-allowed transition-colors text-sm leading-none px-1"
                                                >
                                                  ×
                                                </button>
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </>
                                    )}
                                  </tbody>
                                </table>
                              </div>
                            )}
                            {unassignedBuyItems.length > 0 && (
                              <div className="px-4 py-2 border-t border-gray-700/20">
                                <select
                                  value=""
                                  onChange={(e) => { if (e.target.value) addBuyAccount(e.target.value, acc.id); }}
                                  className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-[11px] text-gray-400 focus:outline-none focus:border-indigo-500 hover:border-gray-600 cursor-pointer"
                                >
                                  <option value="">+ 이 계좌에 매수 종목 추가</option>
                                  {unassignedBuyItems.map((i) => (
                                    <option key={i.ticker} value={i.ticker}>
                                      {i.name} ({i.ticker}) — {Math.abs(Math.round(i.shares_to_trade!))}주
                                    </option>
                                  ))}
                                </select>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {orders.length === 0 && (
                    <p className="text-sm text-gray-400 text-center py-4">
                      실행할 주문이 없습니다. 잔고 조회 후 주문을 선택하세요.
                    </p>
                  )}
                </>
              )}
            </>
          )}

          {/* ── 실행 중 ── */}
          {phase === "executing" && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-300">주문 실행 중...</p>
              <p className="text-xs text-gray-500">매도 주문 처리 후 매수 주문이 진행됩니다.</p>
            </div>
          )}

          {/* ── 결과 ── */}
          {phase === "result" && results.length > 0 && (
            <div className="space-y-4">
              {results.map((result) => (
                <div key={result.account_id} className="border border-gray-700 rounded-xl overflow-hidden">
                  <div className="bg-gray-800/70 px-4 py-2.5 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{result.account_name}</span>
                      {result.is_mock && (
                        <span className="text-xs bg-yellow-900/40 text-yellow-400 border border-yellow-700/50 px-2 py-0.5 rounded">
                          모의투자
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-300">
                      <span className="text-green-400 font-medium">{result.success_count}건 성공</span>
                      {result.fail_count > 0 && (
                        <>, <span className="text-red-400 font-medium">{result.fail_count}건 실패</span></>
                      )}
                    </span>
                  </div>
                  <table className="w-full text-xs">
                    <thead className="bg-gray-800 text-gray-400">
                      <tr>
                        <th className="px-3 py-2 text-left">종목</th>
                        <th className="px-3 py-2 text-center">구분</th>
                        <th className="px-3 py-2 text-center">유형</th>
                        <th className="px-3 py-2 text-right">주수</th>
                        <th className="px-3 py-2 text-center">결과</th>
                        <th className="px-3 py-2 text-left">주문번호 / 사유</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-700/50">
                      {result.orders.map((o, idx) => (
                        <tr key={idx} className="text-white">
                          <td className="px-3 py-2">
                            <div className="font-medium truncate max-w-[120px]">{o.name}</div>
                            <div className="text-gray-400 text-[11px]">{o.ticker}</div>
                          </td>
                          <td className="px-3 py-2 text-center">
                            <SideBadge isBuy={o.side === "BUY"} />
                          </td>
                          <td className="px-3 py-2 text-center">
                            <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
                              o.order_type === "LIMIT"
                                ? "bg-indigo-900/40 text-indigo-300 border border-indigo-700/40"
                                : "bg-gray-700 text-gray-400"
                            }`}>
                              {o.order_type === "LIMIT" ? "지정가" : "시장가"}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-right">{o.quantity}주</td>
                          <td className="px-3 py-2 text-center">
                            <StatusBadge status={o.status} />
                          </td>
                          <td className="px-3 py-2 text-gray-400 max-w-[160px] truncate">
                            {o.order_no ?? o.error_msg ?? "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 푸터 버튼 */}
        <div className="px-6 py-4 border-t border-gray-700 flex justify-end gap-3">
          {phase === "confirm" && (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-300 border border-gray-600 rounded-lg hover:bg-gray-800 transition-colors"
              >
                취소
              </button>
              <button
                onClick={handleExecute}
                disabled={orders.length === 0}
                className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {orderType === "LIMIT" ? "지정가 " : "시장가 "}실행 ({orders.length}건)
              </button>
            </>
          )}
          {phase === "result" && (
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm bg-gray-700 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              닫기
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
