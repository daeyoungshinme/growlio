import type { PortfolioDriftSummary, RebalancingTiming } from "@/api/rebalancing";
import type { TaxSummary } from "@/api/tax";
import { daysUntilYmd, fmtKrw, fmtMonthDay, relativeTime } from "@/utils/format";

/** 진단 행 시점 판정 라벨·색 — 백엔드 `timing_verdict.decide_timing`(plans/136) */
export const TIMING_LABEL: Record<RebalancingTiming, string> = {
  NOW: "지금 실행",
  SPLIT: "분할 실행",
  HOLD: "보류",
  WATCH: "지켜보기",
  OK: "안정",
};

export const TIMING_BADGE: Record<RebalancingTiming, string> = {
  NOW: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  SPLIT: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  HOLD: "bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-200",
  WATCH: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  OK: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
};

export const TIMING_DOT: Record<RebalancingTiming, string> = {
  NOW: "bg-red-500",
  SPLIT: "bg-orange-500",
  HOLD: "bg-gray-400",
  WATCH: "bg-amber-500",
  OK: "bg-green-500",
};

const SCHEDULE_SHORT: Record<string, string> = {
  DAILY: "매일",
  WEEKLY: "매주",
  MONTHLY: "매월",
  QUARTERLY: "분기",
  SEMIANNUAL: "반기",
  ANNUAL: "매년",
};

/** 구버전 응답(timing 없음)은 이탈 여부로 대신한다 */
export function summaryTiming(s: PortfolioDriftSummary): RebalancingTiming {
  if (s.timing) return s.timing;
  return s.needs_rebalancing ? "NOW" : "OK";
}

/**
 * 행 보조 정보 조각 — "마지막 12일 전 · 다음 12/25(매월) · 예상 비용 11만원". 값이 없는 조각은 뺀다.
 * 알림이 없으면 다음 예정 자리에 "알림 없음".
 */
export function timingMetaParts(s: PortfolioDriftSummary): string[] {
  const parts: string[] = [];
  parts.push(
    s.last_rebalanced_at ? `마지막 ${relativeTime(s.last_rebalanced_at)}` : "실행 기록 없음",
  );
  if (s.next_scheduled_date) {
    const days = daysUntilYmd(s.next_scheduled_date);
    const when = days <= 0 ? "오늘" : fmtMonthDay(s.next_scheduled_date);
    const cycle = s.schedule_type ? SCHEDULE_SHORT[s.schedule_type] : undefined;
    parts.push(`다음 ${when}${cycle ? `(${cycle})` : ""}`);
  } else if (s.has_alert_configured === false) {
    parts.push("알림 없음");
  } else if (s.has_alert_configured) {
    parts.push("이탈 시 알림");
  }
  if ((s.estimated_cost_krw ?? 0) > 0) parts.push(`예상 비용 ${fmtKrw(s.estimated_cost_krw ?? 0)}`);
  return parts;
}

/** 헤더 배지 — "지금 2 · 보류 1"처럼 행동이 필요한 판정만 센다. 없으면 null */
export function timingHeadline(summaries: readonly PortfolioDriftSummary[]): string | null {
  const counts: Partial<Record<RebalancingTiming, number>> = {};
  for (const s of summaries) {
    const t = summaryTiming(s);
    counts[t] = (counts[t] ?? 0) + 1;
  }
  const parts = (["NOW", "SPLIT", "HOLD"] as const)
    .filter((t) => counts[t])
    .map((t) => `${TIMING_LABEL[t].replace(" 실행", "")} ${counts[t]}`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

/**
 * 올해 해외 양도세 기본공제 여유 안내 — 해외 매도 이익이 예상되는 리밸런싱의 시점 판단 보조.
 * 여유 = max(0, 공제 − 올해 실현손익)(백엔드 `tax_action_builders` 절세 액션과 같은 식).
 * 실현손익을 모르면(null — 자동 집계 계좌 없음·조회 실패) 지어내지 않고 null.
 */
export function overseasDeductionRoomNote(
  tax: Pick<TaxSummary, "overseas_realized_gain_krw" | "overseas_gain_deduction_krw"> | undefined,
): string | null {
  if (!tax || tax.overseas_realized_gain_krw == null) return null;
  const room = Math.max(0, tax.overseas_gain_deduction_krw - tax.overseas_realized_gain_krw);
  if (room <= 0) {
    return "올해 해외 양도세 기본공제를 이미 다 썼어요 — 해외 매도 이익은 과세돼요. 급하지 않다면 내년 매도도 방법이에요.";
  }
  return `올해 해외 양도세 기본공제 여유 ${fmtKrw(room)} — 이 안의 해외 매도 이익은 세금이 없어요(연내 결제분 기준).`;
}
