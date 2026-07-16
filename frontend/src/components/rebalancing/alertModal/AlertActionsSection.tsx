import { useState } from "react";
import { Bell, BellOff, Loader2, PlayCircle, Send } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sendTestAccountRebalancingAlert, sendTestRebalancingAlert } from "@/api/alerts";
import { quickExecuteRebalancing } from "@/api/rebalancing";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidateRebalancingPlanData } from "@/utils/queryInvalidation";

interface Props {
  form: RebalancingAlertFormState;
  hasAlert: boolean;
  portfolioId: string;
  targetAccountId?: string;
}

export function AlertActionsSection({ form, hasAlert, portfolioId, targetAccountId }: Props) {
  const queryClient = useQueryClient();
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const testMut = useMutation({
    mutationFn: () =>
      targetAccountId
        ? sendTestAccountRebalancingAlert(portfolioId, targetAccountId)
        : sendTestRebalancingAlert(portfolioId),
    onSuccess: (data) => {
      toast(data.message, data.email_sent || data.push_sent ? "success" : "error");
    },
    onError: (e) => {
      toast(extractErrorMessage(e, "테스트 알림 발송에 실패했습니다"), "error");
    },
  });

  // "지금 테스트 실행" — 저장된(또는 화면에 입력된 미저장) 자동화 설정값으로 실제 스케줄 AUTO와
  // 동일한 파이프라인(드리프트 분석 → 대기 플랜 생성 → 계획 안내 이메일 발송)을 지금 바로 태운다.
  // 즉시 체결이 아니라 매수는 대기시간 후 자동 실행, 매도는 이메일 승인이 필요하다.
  const quickExecuteMut = useMutation({
    mutationFn: () =>
      quickExecuteRebalancing(
        portfolioId,
        {
          account_id: form.accountId || undefined,
          strategy: form.strategy,
          order_type: form.orderType,
        },
        targetAccountId,
      ),
    onSuccess: (result) => {
      const toastType = result.status === "MARKET_BLOCKED" ? "error" : "success";
      toast(result.message, toastType);
      if (result.status === "PLAN_GENERATED") {
        void invalidateRebalancingPlanData(queryClient);
      }
    },
    onError: (e) => {
      toast(extractErrorMessage(e, "계획 생성에 실패했습니다"), "error");
    },
  });

  function handleDeleteClick() {
    if (!confirmingDelete) {
      setConfirmingDelete(true);
      setTimeout(() => setConfirmingDelete(false), 3000);
    } else {
      form.deleteMut.mutate();
    }
  }

  return (
    <>
      {/* ── 테스트 알림 발송 ── */}
      {hasAlert && (
        <button
          onClick={() => testMut.mutate()}
          disabled={testMut.isPending}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          {testMut.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
          테스트 알림 발송
        </button>
      )}

      {/* ── 지금 테스트 실행 (AUTO 모드 전용) — 지금 바로 계획을 생성해 이메일로 보낸다.
           매수는 대기 후 자동 실행, 매도는 이메일 승인이 필요하다 (즉시 체결 아님). ── */}
      {hasAlert && form.mode === "AUTO" && form.accountId && (
        <button
          onClick={() => quickExecuteMut.mutate()}
          disabled={quickExecuteMut.isPending}
          className="w-full flex items-center justify-center gap-2 py-2 text-sm border border-orange-300 dark:border-orange-700 text-orange-600 dark:text-orange-400 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-950 disabled:opacity-50 transition-colors"
        >
          {quickExecuteMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <PlayCircle size={14} />
          )}
          지금 테스트 실행
        </button>
      )}

      {/* ── 저장/삭제 ── */}
      <div className="sticky bottom-0 bg-white dark:bg-gray-900 px-6 py-4 -mx-4 border-t border-gray-100 dark:border-gray-700 flex gap-3">
        <button
          onClick={() => form.upsertMut.mutate()}
          disabled={form.isPending}
          aria-busy={form.upsertMut.isPending}
          className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {form.upsertMut.isPending ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <Bell size={14} />
          )}
          {hasAlert ? "설정 업데이트" : "자동화 설정"}
        </button>
        {hasAlert && (
          <button
            onClick={handleDeleteClick}
            disabled={form.isPending}
            className={`flex items-center justify-center gap-1.5 px-4 py-2 text-sm rounded-lg disabled:opacity-50 transition-colors ${
              confirmingDelete
                ? "bg-red-600 text-white hover:bg-red-700 border border-red-600"
                : "border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-950"
            }`}
          >
            {form.deleteMut.isPending ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <BellOff size={14} />
            )}
            {confirmingDelete ? "정말 해제?" : "설정 해제"}
          </button>
        )}
      </div>
    </>
  );
}
