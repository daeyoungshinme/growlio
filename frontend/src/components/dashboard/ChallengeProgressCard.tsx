import { Link } from "react-router-dom";
import { Flame, ChevronRight } from "lucide-react";
import type { Challenge } from "@/api/challenges";
import { clampPct, fmtPct } from "@/utils/format";

import { TOUCH_HEIGHT_MIN } from "@/constants/uiSizes";
interface Props {
  challenges: Challenge[];
}

/** 홈 대시보드 — 진행 중인 적립 챌린지 요약(입금 스트릭 우선). ACTIVE 챌린지가 있을 때만 렌더. */
export default function ChallengeProgressCard({ challenges }: Props) {
  const active = challenges.filter((c) => c.status === "ACTIVE");
  if (active.length === 0) return null;

  // 입금 챌린지를 우선 노출 (스트릭이 습관 지표로 가장 직관적)
  const primary = active.find((c) => c.challenge_type === "DEPOSIT") ?? active[0];
  if (!primary) return null;
  const { progress } = primary;
  const isDeposit = primary.challenge_type === "DEPOSIT";

  // 한 줄 행 — 미입금 경고는 "지금 할 일"·하단 네비 배지가 이미 띄우므로 여기선 습관 지표만 (docs/plans/67 P1-4)
  return (
    <Link
      to="/invest-plan?tab=챌린지"
      className={`card flex items-center gap-3 ${TOUCH_HEIGHT_MIN} active:opacity-70 hover:border-blue-300 dark:hover:border-blue-700 transition-colors`}
    >
      <div className="p-1.5 rounded-lg shrink-0 bg-orange-100/60 dark:bg-orange-900/30">
        <Flame size={16} className="text-orange-500 dark:text-orange-400" aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200 truncate">
          {primary.title}
          {active.length > 1 && (
            <span className="font-normal text-gray-500 dark:text-gray-400">
              {` 외 ${active.length - 1}개`}
            </span>
          )}
        </h2>
        {progress.progress_pct != null && (
          <div className="mt-1.5 w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500 transition-all"
              style={{ width: `${clampPct(progress.progress_pct)}%` }}
            />
          </div>
        )}
      </div>
      {isDeposit ? (
        <div className="shrink-0 text-right">
          <p className="text-sm font-bold text-orange-600 dark:text-orange-400 tabular-nums">
            <span>{progress.current_streak}</span>
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">개월 연속</span>
          </p>
          <p
            className={`text-xs ${
              progress.this_month_satisfied
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-amber-600 dark:text-amber-400"
            }`}
          >
            이번 달 {progress.this_month_satisfied ? "완료" : "미완료"}
          </p>
        </div>
      ) : (
        <p className="shrink-0 text-sm font-bold text-gray-900 dark:text-gray-50 tabular-nums">
          {progress.progress_pct != null ? `${progress.progress_pct.toFixed(0)}%` : "—"}
          <span className="block text-xs font-medium text-gray-500 dark:text-gray-400">
            {primary.challenge_type === "RETURN_PCT"
              ? `현재 ${fmtPct(progress.current_return_pct, 1)}`
              : "달성"}
          </span>
        </p>
      )}
      <ChevronRight size={16} className="text-gray-400 shrink-0" aria-hidden="true" />
    </Link>
  );
}
