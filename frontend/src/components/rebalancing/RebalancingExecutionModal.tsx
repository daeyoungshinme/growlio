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
  fetchKisBalance,
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
  // 비활성 계좌도 포함한 전체 KIS 계좌
  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS");

  // 실시간 잔고: accountId → 포지션 목록
  const [liveBalances, setLiveBalances] = useState<Record<string, KisBalancePosition[]>>({});
  const [balanceState, setBalanceState] = useState<Record<string, BalanceLoadState>>({});
  // 예수금: accountId → deposit_krw
  const [depositKrw, setDepositKrw] = useState<Record<string, number>>({});

  // 계좌별 실시간 잔고 수량 조회 (실시간 우선, 분석 결과 폴백)
  function getAccountQuantity(ticker: string, accountId: string): number {
    const livePos = liveBalances[accountId]?.find((p) => p.ticker === ticker);
    if (livePos !== undefined) return livePos.quantity;
    return (
      (analysis.ticker_account_map[ticker] ?? []).find((a) => a.account_id === accountId)
        ?.quantity ?? 0
    );
  }

  // 계좌가 ticker를 보유하고 있는지 (실시간 또는 분석 결과 기준)
  function accountHoldsTicker(ticker: string, accountId: string): boolean {
    if (liveBalances[accountId]) {
      return liveBalances[accountId].some((p) => p.ticker === ticker && p.quantity > 0);
    }
    return (analysis.ticker_account_map[ticker] ?? []).some(
      (a) => a.account_id === accountId && a.asset_type === "STOCK_KIS" && a.quantity > 0
    );
  }

  // KIS 계좌의 실시간 잔고 로드 (단일 계좌 재조회용)
  async function loadLiveBalance(accountId: string) {
    setBalanceState((prev) => ({ ...prev, [accountId]: "loading" }));
    try {
      const res: KisBalanceResponse = await fetchKisBalance(accountId);
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

  // 모든 KIS 계좌 잔고 일괄 로드
  async function loadAllLiveBalances() {
    if (kisAccounts.length === 0) return;
    const loadingState: Record<string, BalanceLoadState> = {};
    kisAccounts.forEach((acc) => { loadingState[acc.id] = "loading"; });
    setBalanceState(loadingState);

    try {
      const responses = await fetchAllKisBalances();
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

  // 모달 오픈 시 전 계좌 잔고 자동 로딩
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadAllLiveBalances(); }, []);

  // 분석 결과에서 ticker가 KIS 계좌에 있는지 확인 (asset_type 기준)
  function getKisInfos(ticker: string): TickerAccountInfo[] {
    return (analysis.ticker_account_map[ticker] ?? []).filter(
      (a) => a.asset_type === "STOCK_KIS"
    );
  }

  // 기본 매수 계좌: 해당 ticker를 가장 많이 보유한 KIS 계좌, 없으면 첫 번째 계좌
  function primaryKisAccountId(ticker: string): string {
    const defaultId = kisAccounts[0]?.id ?? "";
    const infos = getKisInfos(ticker);
    if (infos.length === 0) return defaultId;
    return infos.reduce((best, a) => (a.quantity > best.quantity ? a : best), infos[0]).account_id;
  }

  const actionableItems = getActionableItems(analysis);

  // 수량 오버라이드
  const [qtyOverrides, setQtyOverrides] = useState<Record<string, number>>({});

  // BUY 계좌 배정: ticker → accountId
  const [buyAccountMap, setBuyAccountMap] = useState<Record<string, string>>(() => {
    const defaultAccId = kisAccounts[0]?.id ?? "";
    const map: Record<string, string> = {};
    if (!defaultAccId) return map;
    actionableItems.forEach((i) => {
      if ((i.shares_to_trade ?? 0) > 0)
        map[i.ticker] = primaryKisAccountId(i.ticker);
    });
    return map;
  });

  // 체크박스 선택
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

  // ── 계좌별 SELL 행 (분석 결과 + 실시간 잔고 병합) ──
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

      // 다중 KIS 계좌 보유 시 비례 분배
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

  // ── 계좌별 BUY 행 ──
  function getBuyRows(accountId: string): {
    item: RebalancingItem;
    suggestedQty: number;
    currentQty: number;
  }[] {
    return actionableItems
      .filter((i) => (i.shares_to_trade ?? 0) > 0 && buyAccountMap[i.ticker] === accountId)
      .map((i) => ({
        item: i,
        suggestedQty: Math.abs(Math.round(i.shares_to_trade!)),
        currentQty: getAccountQuantity(i.ticker, accountId),
      }));
  }

  // ── 미추적 종목 SELL 행 ──
  function getUntrackedSellRows(accountId: string): {
    ticker: string;
    name: string;
    market: string;
    currentQty: number;
    suggestedQty: number;
  }[] {
    const rows: { ticker: string; name: string; market: string; currentQty: number; suggestedQty: number }[] = [];
    for (const h of analysis.untracked_holdings) {
      if (!accountHoldsTicker(h.ticker, accountId)) continue;
      const qty = Math.floor(getAccountQuantity(h.ticker, accountId));
      if (qty > 0) {
        rows.push({ ticker: h.ticker, name: h.name, market: h.market, currentQty: qty, suggestedQty: qty });
      }
    }
    return rows;
  }

  // ── 실행 주문 목록 생성 ──
  function buildOrders(): ExecutionOrderItem[] {
    const orders: ExecutionOrderItem[] = [];
    kisAccounts.forEach((acc) => {
      getSellRows(acc.id).forEach(({ item, suggestedQty }) => {
        const key = `sell_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({ ticker: item.ticker, name: item.name, market: item.market, side: "SELL", quantity: qty, account_id: acc.id });
      });
      getBuyRows(acc.id).forEach(({ item, suggestedQty }) => {
        const key = `buy_${item.ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({ ticker: item.ticker, name: item.name, market: item.market, side: "BUY", quantity: qty, account_id: acc.id });
      });
      getUntrackedSellRows(acc.id).forEach(({ ticker, name, market, suggestedQty }) => {
        const key = `untracked_sell_${ticker}_${acc.id}`;
        if (!selected.has(key)) return;
        const qty = qtyOverrides[key] ?? suggestedQty;
        if (qty > 0)
          orders.push({ ticker, name, market, side: "SELL", quantity: qty, account_id: acc.id });
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

  function reassignBuyAccount(ticker: string, newAccountId: string) {
    const prevAccId = buyAccountMap[ticker];
    if (prevAccId) {
      const prevKey = `buy_${ticker}_${prevAccId}`;
      setSelected((prev) => { const next = new Set(prev); next.delete(prevKey); return next; });
      setQtyOverrides((prev) => { const next = { ...prev }; delete next[prevKey]; return next; });
    }
    setBuyAccountMap((prev) => ({ ...prev, [ticker]: newAccountId }));
    setSelected((prev) => new Set([...prev, `buy_${ticker}_${newAccountId}`]));
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
    const untracked = getUntrackedSellRows(accountId).filter((r) => selected.has(`untracked_sell_${r.ticker}_${accountId}`)).length;
    return { sells: sells + untracked, buys };
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
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

              {errorMsg && (
                <div className="rounded-lg bg-red-900/30 border border-red-700/50 px-4 py-3 text-xs text-red-300">
                  {errorMsg}
                </div>
              )}

              {kisAccounts.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">연결된 KIS 계좌가 없습니다.</p>
              ) : (
                <>
                  {kisAccounts.map((acc) => {
                    const sellRows = getSellRows(acc.id);
                    const buyRows = getBuyRows(acc.id);
                    const untrackedRows = getUntrackedSellRows(acc.id);
                    const bState = balanceState[acc.id] ?? "idle";
                    const hasData = sellRows.length > 0 || buyRows.length > 0 || untrackedRows.length > 0;

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
                            {/* 실시간 잔고 재조회 버튼 */}
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
                          <div className="divide-y divide-gray-700/50">
                            {/* 매도 테이블 */}
                            {sellRows.length > 0 && (
                              <div>
                                <div className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30">매도</div>
                                <table className="w-full text-xs">
                                  <tbody className="divide-y divide-gray-700/30">
                                    {sellRows.map(({ item, currentQty, suggestedQty }) => {
                                      const key = `sell_${item.ticker}_${acc.id}`;
                                      const qty = qtyOverrides[key] ?? suggestedQty;
                                      const est = item.current_price_krw ? item.current_price_krw * qty : null;
                                      return (
                                        <tr key={key} className="hover:bg-gray-800/40 cursor-pointer" onClick={() => toggleKey(key)}>
                                          <td className="px-3 py-2 w-8">
                                            <input
                                              type="checkbox"
                                              checked={selected.has(key)}
                                              onChange={() => toggleKey(key)}
                                              onClick={(e) => e.stopPropagation()}
                                              className="accent-indigo-500"
                                            />
                                          </td>
                                          <td className="px-3 py-2">
                                            <div className="text-white font-medium">{item.ticker}</div>
                                            <div className="text-gray-400 text-[11px] truncate max-w-[130px]">{item.name}</div>
                                            <div className="text-gray-500 text-[11px]">현재 {currentQty.toLocaleString()}주 보유</div>
                                          </td>
                                          <td className="px-3 py-2 text-center">
                                            <SideBadge isBuy={false} />
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
                                            {est != null && (
                                              <div className="text-[11px] text-gray-500 mt-0.5 text-right">≈ {fmtKrw(est)}</div>
                                            )}
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}

                            {/* 매수 테이블 */}
                            {buyRows.length > 0 && (
                              <div>
                                <div className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30">매수</div>
                                <table className="w-full text-xs">
                                  <tbody className="divide-y divide-gray-700/30">
                                    {buyRows.map(({ item, suggestedQty, currentQty }) => {
                                      const key = `buy_${item.ticker}_${acc.id}`;
                                      const qty = qtyOverrides[key] ?? suggestedQty;
                                      const est = item.current_price_krw ? item.current_price_krw * qty : null;
                                      return (
                                        <tr key={key} className="hover:bg-gray-800/40 cursor-pointer" onClick={() => toggleKey(key)}>
                                          <td className="px-3 py-2 w-8">
                                            <input
                                              type="checkbox"
                                              checked={selected.has(key)}
                                              onChange={() => toggleKey(key)}
                                              onClick={(e) => e.stopPropagation()}
                                              className="accent-indigo-500"
                                            />
                                          </td>
                                          <td className="px-3 py-2">
                                            <div className="text-white font-medium">{item.ticker}</div>
                                            <div className="text-gray-400 text-[11px] truncate max-w-[100px]">{item.name}</div>
                                            <div className="text-gray-500 text-[11px]">
                                              {currentQty > 0 ? `현재 ${currentQty.toLocaleString()}주 보유` : "현재 미보유"}
                                            </div>
                                          </td>
                                          <td className="px-3 py-2 text-center">
                                            <SideBadge isBuy={true} />
                                          </td>
                                          <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                            <div className="flex items-center justify-end gap-1">
                                              <input
                                                type="number"
                                                min={0}
                                                value={qty}
                                                onChange={(e) => setQty(key, parseInt(e.target.value) || 0)}
                                                className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-red-400 font-medium focus:outline-none focus:border-indigo-500"
                                              />
                                              <span className="text-gray-400">주</span>
                                            </div>
                                            {est != null && (
                                              <div className="text-[11px] text-gray-500 mt-0.5 text-right">≈ {fmtKrw(est)}</div>
                                            )}
                                          </td>
                                          {kisAccounts.length > 1 && (
                                            <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                              <select
                                                value={acc.id}
                                                onChange={(e) => reassignBuyAccount(item.ticker, e.target.value)}
                                                className="bg-gray-800 border border-gray-600 rounded px-2 py-1 text-[11px] text-white focus:outline-none focus:border-indigo-500 max-w-[120px]"
                                              >
                                                {kisAccounts.map((a) => (
                                                  <option key={a.id} value={a.id}>
                                                    {a.name}{a.is_mock_mode ? " [모의]" : ""}
                                                  </option>
                                                ))}
                                              </select>
                                            </td>
                                          )}
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}

                            {/* 미추적 종목 매도 (선택적) */}
                            {untrackedRows.length > 0 && (
                              <div>
                                <div className="px-4 py-1.5 text-[11px] text-amber-500 bg-amber-900/20 flex items-center gap-1">
                                  ⚠ 미추적 종목 매도 (목표 포트폴리오 외 보유)
                                </div>
                                <table className="w-full text-xs">
                                  <tbody className="divide-y divide-gray-700/30">
                                    {untrackedRows.map(({ ticker, name, currentQty, suggestedQty }) => {
                                      const key = `untracked_sell_${ticker}_${acc.id}`;
                                      const qty = qtyOverrides[key] ?? suggestedQty;
                                      return (
                                        <tr key={key} className="hover:bg-amber-900/10 cursor-pointer" onClick={() => toggleKey(key)}>
                                          <td className="px-3 py-2 w-8">
                                            <input
                                              type="checkbox"
                                              checked={selected.has(key)}
                                              onChange={() => toggleKey(key)}
                                              onClick={(e) => e.stopPropagation()}
                                              className="accent-amber-500"
                                            />
                                          </td>
                                          <td className="px-3 py-2">
                                            <div className="text-amber-300 font-medium">{ticker}</div>
                                            <div className="text-gray-400 text-[11px] truncate max-w-[130px]">{name}</div>
                                            <div className="text-gray-500 text-[11px]">현재 {currentQty.toLocaleString()}주 보유</div>
                                          </td>
                                          <td className="px-3 py-2 text-center">
                                            <SideBadge isBuy={false} />
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
                                          </td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
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
                        <th className="px-3 py-2 text-right">주수</th>
                        <th className="px-3 py-2 text-center">결과</th>
                        <th className="px-3 py-2 text-left">주문번호 / 사유</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-700/50">
                      {result.orders.map((o, idx) => (
                        <tr key={idx} className="text-white">
                          <td className="px-3 py-2">
                            <div className="font-medium">{o.ticker}</div>
                            <div className="text-gray-400 text-[11px] truncate max-w-[120px]">{o.name}</div>
                          </td>
                          <td className="px-3 py-2 text-center">
                            <SideBadge isBuy={o.side === "BUY"} />
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
                실행 ({orders.length}건)
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
