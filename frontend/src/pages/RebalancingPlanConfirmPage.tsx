import { LineChart, Loader2 } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import Button from "@/components/common/Button";
import {
  cancelBuyPlanByToken,
  decideSellPlanByToken,
  fetchPlanPreview,
  type RebalancingPlanItemOut,
} from "@/api/rebalancingPlan";
import { fmtKrwPrice } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";

const REASON_LABEL: Record<string, string> = {
  NOT_FOUND: "존재하지 않는 링크입니다.",
  ALREADY_DECIDED: "이미 처리된 계획입니다.",
  EXPIRED: "만료된 계획입니다.",
};

function ItemsTable({ items }: { items: RebalancingPlanItemOut[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
            <th className="px-3 py-2 text-left font-medium">종목</th>
            <th className="px-3 py-2 text-right font-medium">수량</th>
            <th className="px-3 py-2 text-center font-medium">주문유형</th>
            <th className="px-3 py-2 text-right font-medium">참고가</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => (
            <tr
              key={`${item.ticker}-${idx}`}
              className="border-t border-gray-100 dark:border-gray-800"
            >
              <td className="px-3 py-2">
                <div className="font-medium text-gray-800 dark:text-gray-200">
                  {item.name ?? item.ticker}
                </div>
                <div className="text-xs text-gray-400">{item.ticker}</div>
              </td>
              <td className="px-3 py-2 text-right">{item.quantity.toLocaleString()}주</td>
              <td className="px-3 py-2 text-center text-xs text-gray-500">
                {item.order_type === "LIMIT" ? "지정가" : "시장가"}
              </td>
              <td className="px-3 py-2 text-right">
                {(item.limit_price ?? item.reference_price)
                  ? fmtKrwPrice(item.limit_price ?? item.reference_price ?? 0)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function RebalancingPlanConfirmPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [resultMessage, setResultMessage] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["rebalancing-plan-preview", token],
    queryFn: () => fetchPlanPreview(token),
    enabled: !!token,
    staleTime: 0,
    retry: false,
  });

  const cancelMut = useMutation({
    mutationFn: () => cancelBuyPlanByToken(token),
    onSuccess: (res) => {
      setResultMessage(res.message);
      void refetch();
    },
    onError: (e) => setResultMessage(extractErrorMessage(e, "처리 중 오류가 발생했습니다")),
  });

  const decideMut = useMutation({
    mutationFn: (decision: "APPROVE" | "REJECT") => decideSellPlanByToken(token, decision),
    onSuccess: (res) => {
      setResultMessage(res.message);
      void refetch();
    },
    onError: (e) => setResultMessage(extractErrorMessage(e, "처리 중 오류가 발생했습니다")),
  });

  const leg = data?.leg;
  const isPending = cancelMut.isPending || decideMut.isPending;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4 py-8">
      <div className="w-full max-w-lg bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
        <div className="flex items-center gap-2 mb-6 justify-center">
          <LineChart className="text-blue-600 dark:text-blue-400" size={28} />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Growlio</h1>
        </div>

        {!token ? (
          <p className="text-sm text-center text-gray-500">유효하지 않은 링크입니다.</p>
        ) : isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={24} className="animate-spin text-gray-400" />
          </div>
        ) : !data?.valid || !leg ? (
          <p className="text-sm text-center text-gray-500">
            {REASON_LABEL[data?.reason ?? "NOT_FOUND"]}
          </p>
        ) : (
          <div className="space-y-4">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100">
              {leg.side === "BUY" ? "매수 계획" : "매도 계획 승인"}
              {leg.portfolio_name && ` — ${leg.portfolio_name}`}
            </h2>
            {leg.account_name && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                실행 계좌: {leg.account_name}
              </p>
            )}

            <ItemsTable items={leg.items} />

            {resultMessage ? (
              <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700">
                <p className="text-sm text-blue-700 dark:text-blue-300 text-center">
                  {resultMessage}
                </p>
              </div>
            ) : leg.actionable ? (
              leg.side === "BUY" ? (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {new Date(leg.deadline_at).toLocaleString("ko-KR")}에 자동 실행됩니다.
                  </p>
                  <Button
                    variant="outline"
                    className="w-full justify-center"
                    loading={isPending}
                    onClick={() => cancelMut.mutate()}
                  >
                    매수 취소하기
                  </Button>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {new Date(leg.deadline_at).toLocaleString("ko-KR")}까지 응답이 없으면 자동
                    취소됩니다.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="danger"
                      className="flex-1 justify-center"
                      loading={isPending}
                      onClick={() => decideMut.mutate("APPROVE")}
                    >
                      승인 (매도 실행)
                    </Button>
                    <Button
                      variant="secondary"
                      className="flex-1 justify-center"
                      loading={isPending}
                      onClick={() => decideMut.mutate("REJECT")}
                    >
                      거부
                    </Button>
                  </div>
                </div>
              )
            ) : (
              <p className="text-sm text-center text-gray-500">
                {REASON_LABEL[data.reason ?? ""] ?? `현재 상태: ${leg.status}`}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
