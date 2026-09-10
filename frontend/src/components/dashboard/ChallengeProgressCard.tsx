import { Link } from "react-router-dom";
import { Flame, ChevronRight } from "lucide-react";
import type { Challenge } from "@/api/challenges";
import { fmtPct } from "@/utils/format";

interface Props {
  challenges: Challenge[];
}

/** 홈 대시보드 — 진행 중인 적립 챌린지 요약(입금 스트릭 우선). ACTIVE 챌린지가 있을 때만 렌더. */
export default function ChallengeProgressCard({ challenges }: Props) {
  const active = challenges.filter((c) => c.status === "ACTIVE");
  if (active.length === 0) return null;

  // 입금 챌린지를 우선 노출 (스트릭이 습관 지표로 가장 직관적)
  const primary = active.find((c) => c.challenge_type === "DEPOSIT") ?? active[0];
  const { progress } = primary;
  const isDeposit = primary.challenge_type === "DEPOSIT";

  return (
    <Link
      to="/invest-plan?tab=챌린지"
      className="card block hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-200">적립 챌린지</h2>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
            {primary.title}
            {active.length > 1 && ` 외 ${active.length - 1}개`}
          </p>
        </div>
        <ChevronRight size={18} className="text-gray-400 shrink-0" aria-hidden="true" />
      </div>

      <div className="mt-3 flex items-center gap-4">
        {isDeposit ? (
          <>
            <span className="inline-flex items-center gap-1.5 text-lg font-bold text-orange-600 dark:text-orange-400">
              <Flame size={18} aria-hidden="true" />
              {progress.current_streak}
              <span className="text-sm font-medium text-gray-500 dark:text-gray-400">
                개월 연속
              </span>
            </span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                progress.this_month_satisfied
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                  : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300"
              }`}
            >
              이번 달 {progress.this_month_satisfied ? "완료" : "미완료"}
            </span>
          </>
        ) : (
          <span className="text-lg font-bold text-gray-900 dark:text-gray-50">
            {progress.progress_pct != null ? `${progress.progress_pct.toFixed(0)}%` : "—"}
            <span className="text-sm font-medium text-gray-500 dark:text-gray-400 ml-1">
              {primary.challenge_type === "RETURN_PCT"
                ? `(현재 ${fmtPct(progress.current_return_pct, 1)})`
                : "달성"}
            </span>
          </span>
        )}
      </div>

      {progress.progress_pct != null && (
        <div className="mt-3 w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
          <div
            className="h-full rounded-full bg-blue-500 transition-all"
            style={{ width: `${Math.min(Math.max(progress.progress_pct, 0), 100)}%` }}
          />
        </div>
      )}
    </Link>
  );
}
