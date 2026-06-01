import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import {
  fetchRebalancingExecutionDetail,
  fetchRebalancingHistory,
  RebalancingExecutionSummary,
} from "../../api/rebalancing";
import { QUERY_KEYS } from "../../constants/queryKeys";

const TRIGGER_LABEL: Record<string, string> = {
  MANUAL: "수동",
  AUTO: "자동",
  ONE_CLICK: "원클릭",
};

const TRIGGER_COLOR: Record<string, string> = {
  MANUAL: "bg-gray-700 text-gray-300",
  AUTO: "bg-blue-900 text-blue-300",
  ONE_CLICK: "bg-emerald-900 text-emerald-300",
};

const STRATEGY_LABEL: Record<string, string> = {
  FULL: "매도+매수",
  BUY_ONLY: "매수만",
};

function ExecutionRow({ item }: { item: RebalancingExecutionSummary }) {
  const [open, setOpen] = useState(false);

  const { data: detail, isLoading: loadingDetail } = useQuery({
    queryKey: [...QUERY_KEYS.rebalancingHistory, item.id],
    queryFn: () => fetchRebalancingExecutionDetail(item.id),
    enabled: open,
    staleTime: Infinity,
  });

  return (
    <div className="border border-gray-700 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-750 transition-colors text-left"
      >
        <div className="flex items-center gap-3 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TRIGGER_COLOR[item.triggered_by] ?? "bg-gray-700 text-gray-300"}`}>
            {TRIGGER_LABEL[item.triggered_by] ?? item.triggered_by}
          </span>
          <span className="text-xs text-gray-400">
            {STRATEGY_LABEL[item.strategy] ?? item.strategy}
          </span>
          <span className="text-sm text-gray-200">
            {new Date(item.executed_at).toLocaleString("ko-KR")}
          </span>
        </div>
        <div className="flex items-center gap-4 shrink-0">
          <div className="flex gap-3 text-xs">
            {item.total_success > 0 && (
              <span className="text-emerald-400">성공 {item.total_success}</span>
            )}
            {item.total_fail > 0 && (
              <span className="text-red-400">실패 {item.total_fail}</span>
            )}
            {item.total_skipped > 0 && (
              <span className="text-gray-500">건너뜀 {item.total_skipped}</span>
            )}
          </div>
          {open ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
        </div>
      </button>

      {open && (
        <div className="px-4 pb-4 border-t border-gray-700">
          {loadingDetail ? (
            <div className="flex justify-center py-4">
              <Loader2 size={16} className="animate-spin text-gray-500" />
            </div>
          ) : detail?.results ? (
            detail.results.map((result) => (
              <div key={result.account_id} className="mt-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-gray-300">{result.account_name}</span>
                  {result.is_mock && (
                    <span className="text-xs bg-yellow-900 text-yellow-300 px-1.5 py-0.5 rounded">모의</span>
                  )}
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500">
                      <th className="text-left py-1 pr-3">종목</th>
                      <th className="text-right py-1 pr-3">방향</th>
                      <th className="text-right py-1 pr-3">수량</th>
                      <th className="text-right py-1 pr-3">주문번호</th>
                      <th className="text-right py-1">상태</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.orders.map((order, i) => (
                      <tr key={i} className="border-t border-gray-800">
                        <td className="py-1.5 pr-3 text-gray-200">{order.name} <span className="text-gray-500">({order.ticker})</span></td>
                        <td className={`py-1.5 pr-3 text-right font-medium ${order.side === "BUY" ? "text-red-400" : "text-blue-400"}`}>
                          {order.side === "BUY" ? "매수" : "매도"}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-gray-300">{order.quantity.toLocaleString()}</td>
                        <td className="py-1.5 pr-3 text-right text-gray-500 font-mono">{order.order_no ?? "—"}</td>
                        <td className="py-1.5 text-right">
                          {order.status === "SUCCESS" ? (
                            <span className="text-emerald-400">성공</span>
                          ) : order.status === "FAILED" ? (
                            <span className="text-red-400" title={order.error_msg ?? ""}>실패</span>
                          ) : (
                            <span className="text-gray-500">건너뜀</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))
          ) : (
            <p className="text-xs text-gray-500 mt-3">상세 정보를 불러올 수 없습니다.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function RebalancingHistoryTab() {
  const { data: history = [], isLoading } = useQuery({
    queryKey: QUERY_KEYS.rebalancingHistory,
    queryFn: () => fetchRebalancingHistory(50),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-gray-500">
        <div className="text-4xl mb-3">📋</div>
        <p className="text-sm">아직 실행 이력이 없습니다.</p>
        <p className="text-xs mt-1">리밸런싱을 실행하면 여기에 기록됩니다.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {history.map((item) => (
        <ExecutionRow key={item.id} item={item} />
      ))}
    </div>
  );
}
