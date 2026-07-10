import { DAYS_KO } from "@/constants/rebalancingConfig";
import type { ScheduleType, TriggerCondition } from "@/api/alerts";

export function buildAlertDescription(
  scheduleType: ScheduleType,
  dayOfWeek: number,
  dayOfMonth: number,
  triggerCondition: TriggerCondition,
  threshold: number,
  mode: "NOTIFY" | "AUTO",
  autoExecutionTime?: string,
  notifyTime?: string,
): string {
  const timeLabel = mode === "AUTO" ? (autoExecutionTime ?? "09:00") : (notifyTime ?? "08:30");
  const when =
    scheduleType === "DAILY"
      ? `매일 ${timeLabel}에`
      : scheduleType === "WEEKLY"
        ? `매주 ${DAYS_KO[dayOfWeek]}요일 ${timeLabel}에`
        : scheduleType === "MONTHLY"
          ? `매월 ${dayOfMonth}일 ${timeLabel}에`
          : scheduleType === "QUARTERLY"
            ? `매 3개월 ${dayOfMonth}일 ${timeLabel}에`
            : scheduleType === "SEMIANNUAL"
              ? `매 6개월 ${dayOfMonth}일 ${timeLabel}에`
              : `매년 ${dayOfMonth}일 ${timeLabel}에`;

  const action = mode === "AUTO" ? "자동으로 리밸런싱을 실행합니다." : "알림을 받습니다.";

  if (triggerCondition === "DRIFT_ONLY") {
    return `비중이 ±${threshold.toFixed(1)}% 이상 이탈 시 ${when} ${action}`;
  }
  if (triggerCondition === "SCHEDULE_ONLY") {
    return `${when} 리밸런싱 현황 리포트를 받습니다.`;
  }
  return `${when} 정기 리포트를 받으며, 비중이 ±${threshold.toFixed(1)}% 이탈 시 즉시 ${action}`;
}
