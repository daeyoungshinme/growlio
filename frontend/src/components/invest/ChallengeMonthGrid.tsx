import type { ChallengeMonth } from "@/api/challenges";
import { fmtKrwShort, fmtMonth } from "@/utils/format";

interface Props {
  months: ChallengeMonth[];
  hasTarget: boolean;
}

/** 적립 습관 캘린더 — 월별 달성 상태를 색칠된 셀 그리드로 표시. */
export default function ChallengeMonthGrid({ months, hasTarget }: Props) {
  if (months.length === 0) {
    return <p className="text-xs text-gray-500 dark:text-gray-400">아직 기록된 달이 없어요.</p>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {months.map((m) => {
        const met = hasTarget ? m.target_met : m.satisfied;
        const partial = hasTarget && m.satisfied && !m.target_met;
        const cls = met
          ? "bg-emerald-500 text-white"
          : partial
            ? "bg-amber-400 text-white"
            : "bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-500";
        return (
          <div
            key={m.month}
            title={`${fmtMonth(m.month)} · ${fmtKrwShort(m.net_krw)}`}
            className={`flex flex-col items-center justify-center rounded-md w-11 h-11 text-xs font-medium ${cls}`}
          >
            <span>{Number(m.month.slice(5))}월</span>
            <span aria-hidden="true">{met ? "✓" : partial ? "•" : "—"}</span>
          </div>
        );
      })}
    </div>
  );
}
