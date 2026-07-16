import type { RebalancingAlert } from "@/api/alerts";
import type { RebalancingAlertFormState } from "@/hooks/useRebalancingAlertForm";
import { buildAlertDescription } from "@/utils/rebalancingAlertDescription";

interface Props {
  form: RebalancingAlertFormState;
  alert: RebalancingAlert | null;
}

export function AlertSummarySection({ form, alert }: Props) {
  return (
    <>
      {/* ── 설명 텍스트 ── */}
      <p className="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
        {buildAlertDescription(
          form.scheduleType,
          form.dayOfWeek,
          form.dayOfMonth,
          form.triggerCondition,
          form.threshold,
          form.mode,
          form.autoExecutionTime,
          form.notifyTime,
        )}
      </p>

      {/* ── 현재 설정 표시 ── */}
      {alert && (
        <div className="rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 p-3 text-xs text-blue-700 dark:text-blue-300">
          현재 설정이 활성화되어 있습니다.
          {alert.last_triggered_at && (
            <span className="block mt-0.5 text-blue-500">
              마지막 트리거: {new Date(alert.last_triggered_at).toLocaleString("ko-KR")}
            </span>
          )}
        </div>
      )}
    </>
  );
}
