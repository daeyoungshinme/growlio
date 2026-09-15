import { Link } from "react-router-dom";
import { Flame, X } from "lucide-react";
import { useCollapsible } from "@/hooks/useCollapsible";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

/** 홈 대시보드 — 적립 챌린지가 하나도 없을 때 만들기를 유도하는 카드. X로 닫으면 다시 안 뜸. */
export default function ChallengeEmptyStateCard() {
  const [dismissed, , setDismissed] = useCollapsible(
    false,
    "growlio:dashboard:challenge-empty-state-dismissed",
  );

  if (dismissed) return null;

  return (
    <div className="card flex items-center gap-3">
      <div className="p-1.5 rounded-lg shrink-0 bg-orange-100/60 dark:bg-orange-900/30">
        <Flame size={16} className="text-orange-500 dark:text-orange-400" aria-hidden="true" />
      </div>
      <p className="flex-1 min-w-0 text-sm font-medium text-gray-700 dark:text-gray-200">
        적립 습관을 챌린지로 만들어보세요
      </p>
      <Link
        to="/invest-plan?tab=챌린지"
        className="shrink-0 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
      >
        만들기 →
      </Link>
      <button
        onClick={() => setDismissed(true)}
        aria-label="카드 닫기"
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 -m-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300`}
      >
        <X size={16} />
      </button>
    </div>
  );
}
