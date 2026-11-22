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
  relativeThreshold?: number | null,
): string {
  // 상대 기준(plans/136)이 켜져 있으면 두 기준을 함께 — "±5.0%(또는 목표 대비 25%)"
  const rule = relativeThreshold
    ? `±${threshold.toFixed(1)}%(또는 목표 대비 ${relativeThreshold}%)`
    : `±${threshold.toFixed(1)}%`;
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
    return `비중이 ${rule} 이상 이탈 시 ${when} ${action}`;
  }
  if (triggerCondition === "SCHEDULE_ONLY") {
    return mode === "AUTO" ? `${when} ${action}` : `${when} 리밸런싱 현황 리포트를 받습니다.`;
  }
  return `${when} 정기 리포트를 받으며, 비중이 ${rule} 이탈 시 즉시 ${action}`;
}

/** 자동 실행 거래 방식(plans/145) 한 줄 — 기본값(목표까지·제한 없음·목표 비중 분할)이면 null. */
export function describeTradeOptions(opts: {
  mode: "NOTIFY" | "AUTO";
  triggerCondition: TriggerCondition;
  tradeToBand: boolean;
  minTradeKrw: number | null;
  isDcaAmount: boolean;
  dcaAllocationMode: "TARGET" | "GAP_FIRST";
}): string | null {
  if (opts.mode !== "AUTO") return null;
  const parts: string[] = [];
  if (opts.isDcaAmount && opts.dcaAllocationMode === "GAP_FIRST") {
    parts.push("적립 금액은 목표보다 모자란 종목부터 채웁니다");
  }
  if (opts.tradeToBand && opts.triggerCondition !== "SCHEDULE_ONLY") {
    parts.push("이탈 종목은 허용 범위 경계까지만 거래합니다");
  }
  if (opts.minTradeKrw && opts.minTradeKrw > 0) {
    parts.push(`${opts.minTradeKrw.toLocaleString()}원 미만 주문은 건너뜁니다`);
  }
  return parts.length ? `${parts.join(" · ")}.` : null;
}
