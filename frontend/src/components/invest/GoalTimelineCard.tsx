import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { GoalTimeline } from "@/api/invest";
import { fmtKrw, fmtMonth, fmtPct } from "@/utils/format";
import { useCollapsible } from "@/hooks/useCollapsible";
import CollapsibleSection from "@/components/common/CollapsibleSection";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { goalRecommendationOverallQuery } from "@/api/queryOptions";
import { TOUCH_HEIGHT_MIN } from "@/constants/uiSizes";

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

  // "더 빨리 달성하려면?"은 보조 제안이라 기본 접힘(docs/plans/67 P1-14)
  const [fasterOpen, toggleFaster] = useCollapsible(false, "growlio:goalTimeline:fasterOpen");

  // 전체 추천은 무거운 계산이고 기본 접힌 "더 빨리 달성하려면?" 안에서만 쓰인다 — 펼칠 때만 조회한다
  // (이미 캐시돼 있으면 접혀 있어도 그 값을 쓴다). 예전엔 적립 계획 탭을 열 때마다 불렀다.
  // 단축 시나리오가 없으면 섹션 노출 여부 자체가 추천 결과에 달려 있어 그때는 바로 조회한다.
  const { data: recommendation } = useQuery({
    ...goalRecommendationOverallQuery,
    enabled: fasterOpen || acceleration_scenarios.length === 0,
  });
  const recommendationExpectedReturnPct =
    recommendation?.is_configured && recommendation.expected_return_pct !== null
      ? recommendation.expected_return_pct
      : null;

  // 앞섬/뒤처짐은 손익이 아니라 계획 대비 진척이라 에메랄드/앰버 (docs/plans/67).
  // 예전엔 "계획 대비"(개월)와 "상태"(달성 중/미달) 두 칸이 같은 판정을 반복했다 — 한 칸으로 합침(P1-15)
  const leadLagLabel = () => {
    if (lead_lag_months === null || lead_lag_months === undefined) {
      if (on_track === null) return null;
      return on_track ? (
        <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
          <TrendingUp size={14} /> 계획 달성 중
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
          <TrendingDown size={14} /> 계획 미달
        </span>
      );
    }
    if (lead_lag_months > 0)
      return (
        <span className="flex flex-col gap-0.5">
          <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
            <TrendingUp size={14} />
            {lead_lag_months}개월 앞서고 있음
          </span>
          {actual_expected_goal_date && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {fmtMonth(actual_expected_goal_date)} 달성 예상
            </span>
          )}
        </span>
      );
    if (lead_lag_months < 0)
      return (
        <span className="flex flex-col gap-0.5">
          <span className="text-amber-600 dark:text-amber-400 flex items-center gap-1">
            <TrendingDown size={14} />
            {Math.abs(lead_lag_months)}개월 뒤처지고 있음
          </span>
          {actual_expected_goal_date && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {fmtMonth(actual_expected_goal_date)} 달성 예상
            </span>
          )}
        </span>
      );
    return <span className="text-gray-500 dark:text-gray-400">계획과 정확히 일치</span>;
  };

  return (
    <div className={flat ? undefined : "card"}>
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">
        목표 달성 전망
      </h3>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
        부동산 등 실물자산은 제외, 투자자산 기준
      </p>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">현재 진행률</p>
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
        <div className="col-span-2 sm:col-span-1">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">계획 대비</p>
          <p className="text-sm font-medium mt-1">{leadLagLabel() ?? "—"}</p>
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
                  ? "bg-emerald-500"
                  : on_track === false
                    ? "bg-amber-500"
                    : "bg-gray-400 dark:bg-gray-600"
              }`}
              style={{ width: `${Math.min(current_progress_pct, 100)}%` }}
            />
          </div>
        </div>
      )}

      {(acceleration_scenarios.length > 0 || recommendationExpectedReturnPct !== null) && (
        <div className="mt-4 pt-1 border-t border-gray-100 dark:border-gray-800">
          <CollapsibleSection
            isOpen={fasterOpen}
            onToggle={toggleFaster}
            label="더 빨리 달성하려면?"
            collapsedHint="적립액·수익률을 얼마나 늘리면 몇 년 앞당길 수 있는지"
            buttonClassName={`w-full flex items-center justify-between ${TOUCH_HEIGHT_MIN} text-sm font-semibold text-gray-900 dark:text-gray-50`}
          >
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
                  // 추천 기대수익률 − 필요 수익률(%p) — 둘 중 하나라도 없으면 판정하지 않는다
                  const returnMarginPct =
                    s.required_return_pct !== null && recommendationExpectedReturnPct !== null
                      ? recommendationExpectedReturnPct - s.required_return_pct
                      : null;
                  const achievable = returnMarginPct !== null ? returnMarginPct >= 0 : null;
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
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            적립액을 늘리면
                          </p>
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
                          {returnMarginPct !== null && returnMarginPct >= 0
                            ? "추천 포트폴리오로 달성 가능"
                            : `추천 포트폴리오로는 ${(-(returnMarginPct ?? 0)).toFixed(1)}%p 부족`}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <Link
              to={rebalancingUrl({ tab: "목표 조정", mode: "추천" })}
              className={`flex items-center gap-1.5 ${TOUCH_HEIGHT_MIN} text-xs font-medium text-violet-600 dark:text-violet-400 hover:underline mt-1`}
            >
              수익률을 높이는 포트폴리오 추천 보기 <ArrowRight size={12} />
            </Link>
          </CollapsibleSection>
        </div>
      )}
    </div>
  );
}
