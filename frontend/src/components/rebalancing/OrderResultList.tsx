import { useState } from "react";
import type { ExecutionResult, OrderResult } from "@/api/rebalancing";
import { fmtNativePrice } from "@/utils/format";
import { OrderCancelAction, type CancelOutcome } from "./OrderCancelAction";
import { SideBadge, StatusBadge } from "./RebalancingBadges";

/** 취소 버튼이나 취소 결과 중 보여 줄 것이 있는 주문 — 없으면 쿼리 훅을 쓰는 OrderCancelAction을 그리지 않는다 */
function hasCancelInfo(o: OrderResult): boolean {
  return (!!o.cancelable && !!o.result_id) || !!o.cancel_status;
}

function fmtOrderPrice(price: number | null | undefined, market: string): string {
  if (price == null) return "-";
  return fmtNativePrice(price, market);
}

/** 계좌별 주문 결과(모바일 카드·데스크탑 표) — 실행 직후 결과 화면과 실행 이력 상세가 함께 쓴다. */
export function OrderResultList({ results }: { results: ExecutionResult[] }) {
  // 결과 행 id → 방금 받은 취소 응답. 카드·표 두 벌이 같은 값을 읽는다
  const [cancelOutcomes, setCancelOutcomes] = useState<Record<string, CancelOutcome>>({});
  const cancelProps = (o: OrderResult) => ({
    order: o,
    override: o.result_id ? cancelOutcomes[o.result_id] : undefined,
    onOutcome: (outcome: CancelOutcome) =>
      setCancelOutcomes((prev) => ({ ...prev, [o.result_id!]: outcome })),
  });
  return (
    <div className="space-y-4">
      {results.map((result) => (
        <div
          key={result.account_id}
          className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden"
        >
          <div className="bg-gray-100 dark:bg-gray-800/70 px-4 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900 dark:text-white">
                {result.account_name}
              </span>
              {result.is_mock && (
                <span className="text-xs bg-yellow-100 text-yellow-700 border border-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-400 dark:border-yellow-700/50 px-2 py-0.5 rounded">
                  모의투자
                </span>
              )}
            </div>
            <span className="text-xs text-gray-700 dark:text-gray-300">
              <span className="text-green-600 dark:text-green-400 font-medium">
                {result.success_count}건 성공
              </span>
              {result.fail_count > 0 && (
                <>
                  ,{" "}
                  <span className="text-red-600 dark:text-red-400 font-medium">
                    {result.fail_count}건 실패
                  </span>
                </>
              )}
            </span>
          </div>
          {/* 모바일 카드 뷰 */}
          <div className="sm:hidden divide-y divide-gray-200 dark:divide-gray-700/50">
            {result.orders.map((o, idx) => (
              <div key={idx} className="px-3 py-2.5">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <SideBadge isBuy={o.side === "BUY"} />
                      <p className="font-medium text-gray-900 dark:text-white truncate text-sm">
                        {o.name}
                      </p>
                    </div>
                    <p className="text-gray-500 dark:text-gray-400 text-xs mt-0.5">{o.ticker}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <StatusBadge status={o.status} />
                    <p className="text-gray-700 dark:text-gray-300 text-xs mt-0.5">
                      {o.quantity}주
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-1.5 text-xs text-gray-500 dark:text-gray-400 flex-wrap">
                  <span
                    className={`px-1.5 py-0.5 rounded font-medium text-xs ${o.order_type === "LIMIT" ? "bg-indigo-100 text-indigo-700 border border-indigo-300 dark:bg-indigo-900/40 dark:text-indigo-300 dark:border-indigo-700/40" : "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"}`}
                  >
                    {o.order_type === "LIMIT" ? "지정가" : "시장가"}
                  </span>
                  <span>{fmtOrderPrice(o.price, o.market)}</span>
                </div>
                {/* 실패 사유는 잘리지 않게 전폭 줄로, 주문번호는 증권사 문의용이라 생략 (docs/plans/67 P2-1) */}
                {o.error_msg && (
                  <p className="mt-1 text-xs text-red-600 dark:text-red-400 break-keep">
                    {o.error_msg}
                  </p>
                )}
                {hasCancelInfo(o) && (
                  <div className="mt-1.5">
                    <OrderCancelAction {...cancelProps(o)} />
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 데스크탑 테이블 */}
          <table className="hidden sm:table w-full text-xs">
            <thead className="bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
              <tr>
                <th className="px-3 py-2 text-left">종목</th>
                <th className="px-3 py-2 text-center">구분</th>
                <th className="px-3 py-2 text-center">유형</th>
                <th className="px-3 py-2 text-right">가격</th>
                <th className="px-3 py-2 text-right">주수</th>
                <th className="px-3 py-2 text-center">결과</th>
                <th className="px-3 py-2 text-left">주문번호 / 사유</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700/50">
              {result.orders.map((o, idx) => (
                <tr key={idx} className="text-gray-900 dark:text-white">
                  <td className="px-3 py-2">
                    <div className="font-medium truncate max-w-[120px]">{o.name}</div>
                    <div className="text-gray-500 dark:text-gray-400 text-xs">{o.ticker}</div>
                  </td>
                  <td className="px-3 py-2 text-center">
                    <SideBadge isBuy={o.side === "BUY"} />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                        o.order_type === "LIMIT"
                          ? "bg-indigo-100 text-indigo-700 border border-indigo-300 dark:bg-indigo-900/40 dark:text-indigo-300 dark:border-indigo-700/40"
                          : "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
                      }`}
                    >
                      {o.order_type === "LIMIT" ? "지정가" : "시장가"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">
                    {fmtOrderPrice(o.price, o.market)}
                  </td>
                  <td className="px-3 py-2 text-right">{o.quantity}주</td>
                  <td className="px-3 py-2 text-center">
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="px-3 py-2 text-gray-500 dark:text-gray-400 max-w-[16rem]">
                    {o.order_no && <span className="font-mono">{o.order_no}</span>}
                    {/* 실패 사유는 잘리지 않게 줄바꿈으로 전부 보인다 (docs/plans/67 P2-1) */}
                    {o.error_msg && (
                      <span className="block text-red-600 dark:text-red-400 break-keep">
                        {o.error_msg}
                      </span>
                    )}
                    {hasCancelInfo(o) && (
                      <div className="mt-1">
                        <OrderCancelAction {...cancelProps(o)} />
                      </div>
                    )}
                    {!o.order_no && !o.error_msg && !hasCancelInfo(o) && "-"}
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
