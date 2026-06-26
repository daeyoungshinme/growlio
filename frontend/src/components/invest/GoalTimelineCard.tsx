import { TrendingDown, TrendingUp } from "lucide-react";
import type { GoalTimeline } from "@/api/invest";
import { fmtKrw, fmtMonth } from "@/utils/format";

interface Props {
  timeline: GoalTimeline;
  goalAmount: number | null;
}

export default function GoalTimelineCard({ timeline, goalAmount }: Props) {
  const {
    months_to_goal,
    expected_goal_date,
    actual_expected_goal_date,
    current_progress_pct,
    on_track,
    lead_lag_months,
  } = timeline;

  const leadLagLabel = () => {
    if (lead_lag_months === null || lead_lag_months === undefined) return null;
    if (lead_lag_months > 0)
      return (
        <span className="flex flex-col gap-0.5">
          <span className="text-red-500 flex items-center gap-1">
            <TrendingUp size={14} />
            {lead_lag_months}개월 앞서고 있음
          </span>
          {actual_expected_goal_date && (
            <span className="text-xs text-red-400 hidden sm:block">
              {fmtMonth(actual_expected_goal_date)} 달성 예상
            </span>
          )}
        </span>
      );
    if (lead_lag_months < 0)
      return (
        <span className="flex flex-col gap-0.5">
          <span className="text-blue-500 flex items-center gap-1">
            <TrendingDown size={14} />
            {Math.abs(lead_lag_months)}개월 뒤처지고 있음
          </span>
          {actual_expected_goal_date && (
            <span className="text-xs text-blue-400 hidden sm:block">
              {fmtMonth(actual_expected_goal_date)} 달성 예상
            </span>
          )}
        </span>
      );
    return <span className="text-gray-500 dark:text-gray-400">계획과 정확히 일치</span>;
  };

  return (
    <div className="card">
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-4">
        목표 달성 전망
      </h3>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">현재 진행율</p>
          <p className="text-xl font-bold text-gray-900 dark:text-gray-50">
            {current_progress_pct !== null ? `${current_progress_pct.toFixed(1)}%` : "—"}
          </p>
          {goalAmount && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              목표 {fmtKrw(goalAmount)}
            </p>
          )}
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">목표 달성 예상</p>
          <p className="text-xl font-bold text-gray-900 dark:text-gray-50">
            {expected_goal_date ?? "—"}
          </p>
          {months_to_goal && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              약 {months_to_goal}개월 후
            </p>
          )}
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">계획 대비</p>
          <p className="text-sm font-medium mt-1">{leadLagLabel() ?? "—"}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">상태</p>
          {on_track === null ? (
            <p className="text-sm text-gray-400 dark:text-gray-500">데이터 없음</p>
          ) : on_track ? (
            <span className="inline-flex items-center gap-1 text-sm font-medium text-red-500">
              <TrendingUp size={14} /> 계획 달성 중
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 text-sm font-medium text-blue-500">
              <TrendingDown size={14} /> 계획 미달
            </span>
          )}
        </div>
      </div>

      {current_progress_pct !== null && (
        <div className="mt-4">
          <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
            <span>0%</span>
            <span>100%</span>
          </div>
          <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                on_track === true
                  ? "bg-red-500"
                  : on_track === false
                    ? "bg-blue-500"
                    : "bg-gray-400 dark:bg-gray-600"
              }`}
              style={{ width: `${Math.min(current_progress_pct, 100)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
