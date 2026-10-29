import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cancelExecutionOrder, type OrderResult } from "@/api/rebalancing";
import ConfirmModal from "@/components/common/ConfirmModal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

type CancelOutcome = Pick<OrderResult, "cancel_status" | "cancel_message">;

/** 주문 한 건의 미체결 취소 버튼 + 취소 결과 표시 (plans/89).
 * 실행 직후 결과 화면은 쿼리가 아니라 로컬 결과를 그리므로, 응답을 로컬 상태로도 반영한다. */
export function OrderCancelAction({ order }: { order: OrderResult }) {
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  // 방금 받은 응답 — 없으면 props(이력 재조회 결과)를 그대로 쓴다
  const [override, setOverride] = useState<CancelOutcome | null>(null);
  const outcome: CancelOutcome = override ?? {
    cancel_status: order.cancel_status,
    cancel_message: order.cancel_message,
  };

  const { mutate, isPending } = useMutation({
    mutationFn: () => cancelExecutionOrder(order.result_id!),
    onSuccess: (res) => {
      const canceled = res.cancel_status === "CANCELED";
      setOverride({
        cancel_status: res.cancel_status,
        cancel_message: canceled ? null : res.message,
      });
      toast(res.message, canceled ? "success" : "error");
      void qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingHistory });
    },
    onError: (err) => toast(extractErrorMessage(err, "주문을 취소하지 못했습니다."), "error"),
  });

  const canceled = outcome.cancel_status === "CANCELED";
  const showButton = !!order.cancelable && !!order.result_id && !canceled;

  return (
    <div className="flex flex-col items-start gap-0.5">
      {canceled && (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
          미체결 취소됨
        </span>
      )}
      {outcome.cancel_status === "CANCEL_FAILED" && outcome.cancel_message && (
        <span className="text-xs text-red-600 dark:text-red-400 break-keep">
          취소 실패: {outcome.cancel_message}
        </span>
      )}
      {showButton && (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          disabled={isPending}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-500 dark:hover:text-red-300 disabled:opacity-50`}
        >
          {isPending ? "취소 요청 중…" : "미체결 취소"}
        </button>
      )}
      {confirming && (
        <ConfirmModal
          message={`${order.name} ${order.side === "BUY" ? "매수" : "매도"} 주문 중 아직 체결되지 않은 수량을 취소하시겠습니까? 이미 체결된 수량은 취소되지 않습니다.`}
          confirmLabel="미체결 취소"
          cancelLabel="닫기"
          onConfirm={() => {
            setConfirming(false);
            mutate();
          }}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  );
}
