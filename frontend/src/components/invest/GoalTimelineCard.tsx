import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { GoalTimeline } from "@/api/invest";
import { fetchOverallGoalRecommendation } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fmtKrw, fmtMonth, fmtPct } from "@/utils/format";

interface Props {
  timeline: GoalTimeline;
  goalAmount: number | null;
  flat?: boolean;
}

export default function GoalTimelineCard({ timeline, goalAmount, flat }: Props) {
  const {
    months_to_goal,
    expected_goal_date,
    actual_expected_goal_date,
    current_progress_pct,
    on_track,
    lead_lag_months,
    acceleration_scenarios,
  } = timeline;

  const { data: recommendation } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    staleTime: STALE_TIME.LONG,
  });
  const recommendationExpectedReturnPct =
    recommendation?.is_configured && recommendation.expected_return_pct !== null
      ? recommendation.expected_return_pct
      : null;

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
    <div className={flat ? undefined : "card"}>
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

      {(acceleration_scenarios.length > 0 || recommendationExpectedReturnPct !== null) && (
        <div className="mt-5 pt-4 border-t border-gray-100 dark:border-gray-800">
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            더 빨리 달성하려면?
          </h4>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 mb-3">
            지출을 줄이거나 소득을 늘려 적립액을 키우면 목표를 더 빨리 달성할 수 있어요.
          </p>

          {recommendation?.is_configured && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 mb-3 p-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500">목표 달성 필요 수익률</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                  {fmtPct(recommendation.required_return_pct)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  추천 포트폴리오 기대수익률
                </p>
                <p className="text-sm font-semibold text-indigo-600 dark:text-indigo-400">
                  {fmtPct(recommendation.expected_return_pct)}
                </p>
              </div>
              <p className="col-span-2 text-xs text-gray-400 dark:text-gray-500">
                추천 종목 {recommendation.recommended_items.length}개
              </p>
            </div>
          )}

          {acceleration_scenarios.length > 0 && (
            <div className="space-y-2">
              {acceleration_scenarios.map((s) => {
                const achievable =
                  s.required_return_pct !== null && recommendationExpectedReturnPct !== null
                    ? recommendationExpectedReturnPct >= s.required_return_pct
                    : null;
                return (
                  <div
                    key={s.years_earlier}
                    className="p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800 space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-gray-900 dark:text-gray-50">
                        {s.years_earlier}년 앞당기기
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {fmtMonth(s.new_expected_goal_date)} 달성
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">적립액을 늘리면</p>
                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                          월 {fmtKrw(s.required_monthly_deposit)}
                        </p>
                        <p className="text-xs text-amber-600 dark:text-amber-400">
                          +{fmtKrw(s.extra_monthly_deposit)}/월 (연{" "}
                          {fmtKrw(s.required_annual_deposit)})
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          또는 수익률을 높이면
                        </p>
                        {s.required_return_pct !== null ? (
                          <>
                            <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                              연 {s.required_return_pct}%
                            </p>
                            <p className="text-xs text-amber-600 dark:text-amber-400">
                              +{s.extra_return_pct}%p
                            </p>
                          </>
                        ) : (
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            이 방법으로는 달성이 어려워요
                          </p>
                        )}
                      </div>
                    </div>
                    {achievable !== null && (
                      <p
                        className={`text-xs font-medium ${achievable ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-500"}`}
                      >
                        {achievable
                          ? "추천 포트폴리오로 달성 가능"
                          : `추천 포트폴리오로는 ${(s.required_return_pct! - recommendationExpectedReturnPct!).toFixed(1)}%p 부족`}
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <Link
            to="/rebalancing?rtab=포트폴리오"
            className="flex items-center gap-1.5 text-xs font-medium text-violet-600 dark:text-violet-400 hover:underline mt-3"
          >
            수익률을 높이는 포트폴리오 추천 보기 <ArrowRight size={12} />
          </Link>
        </div>
      )}
    </div>
  );
}
