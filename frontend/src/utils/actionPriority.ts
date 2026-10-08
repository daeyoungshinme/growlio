import { daysUntilYmd, parseYmd } from "@/utils/format";

export type ActionPriority = "HIGH" | "MEDIUM" | "LOW";

/** 행동 항목 우선순위 배지 — 절세 액션 플랜(`TaxActionPlanCard`)과 홈 "지금 할 일"(`ActionItemsCard`) 공용. */
export const ACTION_PRIORITY_STYLE: Record<ActionPriority, { label: string; className: string }> = {
  HIGH: {
    label: "우선",
    className: "bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400",
  },
  MEDIUM: {
    label: "권장",
    className: "bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-400",
  },
  LOW: {
    label: "참고",
    className: "bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400",
  },
};

/** "12/31까지 (D-5)" / 지났으면 "12/31 마감" */
export function deadlineLabel(iso: string): string {
  const { month: m, day: d } = parseYmd(iso);
  const days = daysUntilYmd(iso);
  return days >= 0 ? `${m}/${d}까지 (D-${days})` : `${m}/${d} 마감`;
}
