import { useState } from "react";
import { AssetAccount } from "../../api/assets";
import {
  ExecutionOrderItem,
  ExecutionResult,
  OrderResult,
  RebalancingAnalysis,
  RebalancingItem,
  executeRebalancing,
} from "../../api/rebalancing";

interface Props {
  portfolioId: string;
  analysis: RebalancingAnalysis;
  kisAccounts: AssetAccount[];
  onClose: () => void;
}

type Phase = "confirm" | "executing" | "result";

function toOrders(items: RebalancingItem[], selected: Set<string>): ExecutionOrderItem[] {
  return items
    .filter(
      (i) =>
        i.ticker !== "CASH" &&
        i.market !== "KR_PROPERTY" &&
        i.shares_to_trade !== null &&
        Math.abs(i.shares_to_trade) >= 1 &&
        selected.has(i.ticker)
    )
    .map((i) => ({
      ticker: i.ticker,
      name: i.name,
      market: i.market,
      side: i.shares_to_trade! > 0 ? "BUY" : "SELL",
      quantity: Math.abs(Math.round(i.shares_to_trade!)),
    }));
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

export function RebalancingExecutionModal({ portfolioId, analysis, kisAccounts, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("confirm");
  const [selectedAccountId, setSelectedAccountId] = useState(kisAccounts[0]?.id ?? "");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(getActionableItems(analysis).map((i) => i.ticker))
  );
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const selectedAccount = kisAccounts.find((a) => a.id === selectedAccountId);
  const actionableItems = getActionableItems(analysis);
  const orders = toOrders(analysis.items, selected);

  function toggleItem(ticker: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === actionableItems.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(actionableItems.map((i) => i.ticker)));
    }
  }

  async function handleExecute() {
    if (orders.length === 0 || !selectedAccountId) return;
    setPhase("executing");
    setErrorMsg(null);
    try {
      const res = await executeRebalancing(portfolioId, {
        account_id: selectedAccountId,
        orders,
      });
      setResult(res);
      setPhase("result");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "주문 실행 중 오류가 발생했습니다.";
      setErrorMsg(msg);
      setPhase("confirm");
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
          <h2 className="text-base font-semibold text-white">리밸런싱 실행</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
          {/* ── 확인 단계 ── */}
          {phase === "confirm" && (
            <>
              {/* 계좌 선택 */}
              <div>
                <label className="text-xs text-gray-400 mb-1 block">실행 계좌</label>
                <select
                  value={selectedAccountId}
                  onChange={(e) => setSelectedAccountId(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-indigo-500"
                >
                  {kisAccounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                      {a.kis_account_no ? ` (${a.kis_account_no})` : ""}
                      {a.is_mock_mode ? " [모의]" : " [실계좌]"}
                    </option>
                  ))}
                </select>
              </div>

              {/* 경고 배너 */}
              <div className="rounded-lg bg-yellow-900/30 border border-yellow-700/50 px-4 py-3 text-xs text-yellow-300">
                주문이 즉시 체결됩니다. 내용을 신중히 확인하세요.
              </div>

              {selectedAccount && !selectedAccount.is_mock_mode && (
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

              {/* 주문 목록 테이블 */}
              {actionableItems.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-4">실행할 주문이 없습니다.</p>
              ) : (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-400">주문 목록</span>
                    <button
                      onClick={toggleAll}
                      className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      {selected.size === actionableItems.length ? "전체 해제" : "전체 선택"}
                    </button>
                  </div>
                  <div className="border border-gray-700 rounded-lg overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-800 text-gray-400">
                        <tr>
                          <th className="px-3 py-2 text-left w-8"></th>
                          <th className="px-3 py-2 text-left">종목</th>
                          <th className="px-3 py-2 text-center">구분</th>
                          <th className="px-3 py-2 text-right">주수</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-700/50">
                        {actionableItems.map((item) => {
                          const isBuy = item.shares_to_trade! > 0;
                          return (
                            <tr
                              key={item.ticker}
                              className="hover:bg-gray-800/50 cursor-pointer"
                              onClick={() => toggleItem(item.ticker)}
                            >
                              <td className="px-3 py-2">
                                <input
                                  type="checkbox"
                                  checked={selected.has(item.ticker)}
                                  onChange={() => toggleItem(item.ticker)}
                                  onClick={(e) => e.stopPropagation()}
                                  className="accent-indigo-500"
                                />
                              </td>
                              <td className="px-3 py-2">
                                <div className="text-white font-medium">{item.ticker}</div>
                                <div className="text-gray-400 text-[11px] truncate max-w-[160px]">{item.name}</div>
                              </td>
                              <td className="px-3 py-2 text-center">
                                <span className={`font-medium ${isBuy ? "text-red-400" : "text-blue-400"}`}>
                                  {isBuy ? "매수" : "매도"}
                                </span>
                              </td>
                              <td className="px-3 py-2 text-right">
                                <span className={`font-medium ${isBuy ? "text-red-400" : "text-blue-400"}`}>
                                  {Math.abs(Math.round(item.shares_to_trade!))}주
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
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
          {phase === "result" && result && (
            <>
              <div className="flex items-center gap-3">
                <span className="text-sm text-gray-300">
                  총 {result.orders.length}건 중{" "}
                  <span className="text-green-400 font-medium">{result.success_count}건 성공</span>
                  {result.fail_count > 0 && (
                    <>, <span className="text-red-400 font-medium">{result.fail_count}건 실패</span></>
                  )}
                </span>
                {result.is_mock && (
                  <span className="text-xs bg-yellow-900/40 text-yellow-400 border border-yellow-700/50 px-2 py-0.5 rounded">
                    모의투자
                  </span>
                )}
              </div>

              <div className="border border-gray-700 rounded-lg overflow-hidden">
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
                          <span className={o.side === "BUY" ? "text-red-400" : "text-blue-400"}>
                            {o.side === "BUY" ? "매수" : "매도"}
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
            </>
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
