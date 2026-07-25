import { Loader2 } from "lucide-react";
import type { SuggestedGoalCandidate } from "@/api/rebalancing";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

/** 배당 목표를 등록된 후보만으로 달성(또는 개선)할 수 없을 때 제안되는 미등록 고배당 후보 목록 —
 * 승인(추가) 전까지는 비중 계산에 반영되지 않으므로, 사용자가 명시적으로 눌러야 한다. */
export default function SuggestedCandidatesBlock({
  candidates,
  onAdd,
  isPending,
}: {
  candidates: SuggestedGoalCandidate[];
  onAdd: () => void;
  isPending: boolean;
}) {
  if (candidates.length === 0) return null;
  return (
    <div className="pt-1 flex items-center gap-1.5 flex-wrap">
      {candidates.map((c) => (
        <span
          key={`${c.ticker}-${c.market}`}
          className="text-xs bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/50 text-amber-700 dark:text-amber-400 rounded-full px-2 py-0.5"
        >
          {c.name}
          {c.dividend_yield_pct != null && ` (연 ${c.dividend_yield_pct.toFixed(1)}%)`}
        </span>
      ))}
      <button
        type="button"
        disabled={isPending}
        onClick={onAdd}
        className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs font-medium text-amber-700 dark:text-amber-400 border border-amber-300 dark:border-amber-700 hover:bg-amber-50 dark:hover:bg-amber-950/40 disabled:opacity-50 px-2.5 py-1 rounded-lg transition-colors`}
      >
        {isPending && <Loader2 size={12} className="animate-spin" />}
        후보에 추가
      </button>
    </div>
  );
}
