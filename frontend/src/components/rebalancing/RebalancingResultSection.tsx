import type { ExecutionResult } from "@/api/rebalancing";
import { SideBadge, StatusBadge } from "./RebalancingBadges";

interface Props {
  results: ExecutionResult[];
}

export function RebalancingResultSection({ results }: Props) {
  if (results.length === 0) return null;
  return (
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
                <>
                  , <span className="text-red-400 font-medium">{result.fail_count}건 실패</span>
                </>
              )}
            </span>
          </div>
          {/* 모바일 카드 뷰 */}
          <div className="sm:hidden divide-y divide-gray-700/50">
            {result.orders.map((o, idx) => (
              <div key={idx} className="px-3 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <SideBadge isBuy={o.side === "BUY"} />
                      <p className="font-medium text-white truncate text-sm">{o.name}</p>
                    </div>
                    <p className="text-gray-400 text-xs mt-0.5">{o.ticker}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <StatusBadge status={o.status} />
                    <p className="text-gray-300 text-xs mt-0.5">{o.quantity}주</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-400 flex-wrap">
                  <span
                    className={`px-1.5 py-0.5 rounded font-medium text-[11px] ${o.order_type === "LIMIT" ? "bg-indigo-900/40 text-indigo-300 border border-indigo-700/40" : "bg-gray-700 text-gray-400"}`}
                  >
                    {o.order_type === "LIMIT" ? "지정가" : "시장가"}
                  </span>
                  {(o.order_no ?? o.error_msg) && (
                    <span className="truncate max-w-[160px]">{o.order_no ?? o.error_msg}</span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* 데스크탑 테이블 */}
          <table className="hidden sm:table w-full text-xs">
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
                    <span
                      className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
                        o.order_type === "LIMIT"
                          ? "bg-indigo-900/40 text-indigo-300 border border-indigo-700/40"
                          : "bg-gray-700 text-gray-400"
                      }`}
                    >
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
  );
}
