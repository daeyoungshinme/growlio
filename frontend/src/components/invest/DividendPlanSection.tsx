import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, CalendarRange, Settings2, TrendingUp } from "lucide-react";
import { fetchDividendPlan } from "@/api/invest";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fmtKrw, fmtPct } from "@/utils/format";
import SkeletonCard from "@/components/common/SkeletonCard";
import { MONTH_LABELS } from "@/utils/dividendUtils";
import { useCollapsible } from "@/hooks/useCollapsible";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import MonthlyOptimizationCard from "@/components/portfolio/MonthlyOptimizationCard";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { goalRecommendationOverallQuery } from "@/api/queryOptions";
import { TOUCH_HEIGHT_MIN, TOUCH_HEIGHT_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { portfolioUrl } from "@/utils/tabUrl";

interface Props {
  onOpenSettings: () => void;
}

function AchievementValue({ pct, sizeClass }: { pct: number | null; sizeClass: string }) {
  const achieved = (pct ?? 0) >= 100;
  return (
    <>
      <p
        className={`${sizeClass} font-bold ${
          achieved ? "text-emerald-600 dark:text-emerald-400" : "text-blue-500"
        }`}
      >
        {pct !== null ? `${pct.toFixed(1)}%` : "—"}
      </p>
      {achieved && (
        <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 mt-0.5">
          <TrendingUp size={12} /> 목표 달성
        </span>
      )}
    </>
  );
}

export default function DividendPlanSection({ onOpenSettings }: Props) {
  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.dividendPlan,
    queryFn: fetchDividendPlan,
    staleTime: STALE_TIME.MEDIUM,
  });

  // GoalTimelineCard(적립 계획 탭)와 동일한 queryKey를 써서 캐시를 공유한다 — 중복 호출 없음.
  const { data: recommendation } = useQuery(goalRecommendationOverallQuery);
  // 월별 균등화 추천은 실적(자산 › 배당)이 아니라 계획 행동이라 여기 둔다. 접힌 동안엔 조회하지 않는다.
  const [optimizationOpen, toggleOptimization] = useCollapsible(
    false,
    "growlio:dividendPlan:monthlyOptimizationOpen",
  );

  // "더 빨리 달성하려면?"은 보조 제안이라 기본 접힘 — 적립 계획 탭의 같은 블록과 함께 화면 길이를 줄인다(docs/plans/67 P1-14)
  const [fasterOpen, toggleFaster] = useCollapsible(false, "growlio:dividendPlan:fasterOpen");

  if (isLoading) return <SkeletonCard rows={5} height="h-5" />;

  if (isError || !data) {
    return (
      <div className="card text-sm text-red-600 dark:text-red-400">
        배당 계획 데이터를 불러오지 못했습니다.
      </div>
    );
  }

  const {
    annual_dividend_goal,
    estimated_annual_krw,
    estimated_monthly_krw,
    actual_annual_received_krw,
    goal_achievement_pct,
    required_dividend_yield_pct,
    current_dividend_yield_pct,
    monthly_projected,
  } = data;

  // 평균 예상 배당금 (약한 달 판정용)
  const avgProjected = monthly_projected.reduce((s, p) => s + p.amount_krw, 0) / 12;
  const weakMonths =
    avgProjected > 0
      ? monthly_projected
          .filter((p) => p.amount_krw < avgProjected * 0.5)
          .map((p) => MONTH_LABELS[p.month - 1])
      : [];

  const progressPct = goal_achievement_pct !== null ? Math.min(goal_achievement_pct, 100) : null;

  return (
    <div className="space-y-5">
      {/* 배당 목표 달성 카드 */}
      <div className="card">
        <div className="flex items-start justify-between mb-1">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            배당 목표 달성 현황
          </h3>
          <button
            onClick={onOpenSettings}
            className={`shrink-0 flex items-center gap-2 px-4 py-2 ${TOUCH_HEIGHT_MIN_MOBILE_ONLY} text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
          >
            <Settings2 size={15} />
            설정 편집
          </button>
        </div>
        <div className="text-right mb-4">
          <Link
            to={portfolioUrl("배당")}
            className={`inline-flex items-center ${TOUCH_HEIGHT_MIN} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
          >
            종목별 배당 내역 보기
          </Link>
        </div>

        {annual_dividend_goal ? (
          <>
            {/* 모바일: 달성률 히어로 + 보조 3열 */}
            <div className="sm:hidden mb-4">
              <div className="flex items-start justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-xl mb-3">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">배당 달성률</p>
                  <AchievementValue pct={goal_achievement_pct} sizeClass="text-3xl" />
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">목표</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                    {fmtKrw(annual_dividend_goal)}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    월 {fmtKrw(annual_dividend_goal / 12)}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 leading-tight">
                    예상 연배당
                  </p>
                  <p className="text-sm font-bold text-red-500">{fmtKrw(estimated_annual_krw)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 leading-tight">
                    월 평균
                  </p>
                  <p className="text-sm font-bold text-gray-900 dark:text-gray-50">
                    {fmtKrw(estimated_monthly_krw)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 leading-tight">
                    올해 실수령
                  </p>
                  <p className="text-sm font-bold text-gray-900 dark:text-gray-50">
                    {fmtKrw(actual_annual_received_krw)}
                  </p>
                </div>
              </div>
            </div>

            {/* 데스크탑: 기존 4열 */}
            <div className="hidden sm:grid sm:grid-cols-4 gap-4 mb-4">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">목표 연배당</p>
                <p className="text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(annual_dividend_goal)}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  월 {fmtKrw(annual_dividend_goal / 12)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">현재 예상 연배당</p>
                <p className="text-xl font-bold text-red-500">{fmtKrw(estimated_annual_krw)}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  월 평균 {fmtKrw(estimated_monthly_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">올해 실수령</p>
                <p className="text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(actual_annual_received_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">달성률</p>
                <AchievementValue pct={goal_achievement_pct} sizeClass="text-xl" />
              </div>
            </div>

            {required_dividend_yield_pct !== null && (
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 mb-4 p-2.5 rounded-lg bg-indigo-50 dark:bg-indigo-950">
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    목표 달성에 필요한 배당수익률
                  </p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                    {fmtPct(required_dividend_yield_pct)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500">현재 예상 배당수익률</p>
                  <p className="text-sm font-semibold text-indigo-600 dark:text-indigo-400">
                    {fmtPct(current_dividend_yield_pct)}
                  </p>
                </div>
              </div>
            )}

            {progressPct !== null && (
              <div>
                {/* 달성률 %는 바로 위 수치와 중복이라 막대만 (docs/plans/67 P1-13) */}
                <div className="h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      progressPct >= 100 ? "bg-emerald-500" : "bg-blue-500"
                    }`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  목표까지 {fmtKrw(Math.max(0, annual_dividend_goal - estimated_annual_krw))} 부족
                </p>
              </div>
            )}
          </>
        ) : (
          <div className="py-2">
            <div className="p-3 bg-blue-50 dark:bg-blue-950 rounded-xl mb-4 text-sm text-gray-600 dark:text-gray-400">
              배당 목표를 설정하면 달성률을 확인할 수 있습니다.{" "}
              <button
                onClick={onOpenSettings}
                className="underline font-medium text-gray-700 dark:text-gray-300"
              >
                지금 설정하기
              </button>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">예상 연배당</p>
                <p className="text-base sm:text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(estimated_annual_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">예상 월평균</p>
                <p className="text-base sm:text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(estimated_monthly_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">올해 실수령</p>
                <p className="text-base sm:text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(actual_annual_received_krw)}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 배당 목표 달성 추천 ETF — 적립 계획 탭의 "더 빨리 달성하려면?"과 동일한 사상 */}
      {annual_dividend_goal && recommendation?.is_configured && (
        <CollapsibleCard
          icon={TrendingUp}
          iconWrapClassName="bg-violet-50 dark:bg-violet-950"
          iconColorClassName="text-violet-600 dark:text-violet-400"
          title="배당 목표를 더 빨리 달성하려면?"
          isOpen={fasterOpen}
          onToggle={toggleFaster}
          collapsedHint={recommendation.note ?? "배당수익률이 높은 ETF 후보를 추천해요"}
        >
          {/* 위 달성 현황의 "필요 배당수익률"과 같은 축 — 칸 2개 대신 한 줄 비교 (docs/plans/67 P1-13) */}
          <p className="text-xs text-gray-600 dark:text-gray-300 mb-2">
            추천 비중의 기대 배당수익률{" "}
            <span className="font-semibold text-indigo-600 dark:text-indigo-400">
              {fmtPct(recommendation.expected_dividend_yield_pct)}
            </span>{" "}
            · 목표{" "}
            <span className="font-semibold text-gray-900 dark:text-gray-50">
              {fmtPct(recommendation.required_dividend_yield_pct)}
            </span>
          </p>

          {recommendation.note && (
            <p
              className={`text-xs font-medium mb-2 ${
                recommendation.dividend_goal_status === "unreachable"
                  ? "text-amber-600 dark:text-amber-400"
                  : recommendation.dividend_goal_status === "improvable"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-gray-500 dark:text-gray-400"
              }`}
            >
              {recommendation.note}
            </p>
          )}

          {/* 후보 추가 같은 편집은 목표 조정 › 추천 한 곳에서 — 여기는 요약만(계획 106 C1) */}
          {recommendation.suggested_candidates.length > 0 && (
            <p className="text-xs text-gray-600 dark:text-gray-300">
              제안 고배당 후보 {recommendation.suggested_candidates.map((c) => c.name).join(", ")}
            </p>
          )}

          <Link
            to={rebalancingUrl({ tab: "목표 조정", mode: "추천" })}
            className={`flex items-center gap-1.5 ${TOUCH_HEIGHT_MIN} text-xs font-medium text-violet-600 dark:text-violet-400 hover:underline`}
          >
            {recommendation.suggested_candidates.length > 0
              ? "목표 조정에서 후보 추가·추천 비중 보기"
              : "추천 포트폴리오 자세히 보기"}{" "}
            <ArrowRight size={12} />
          </Link>
        </CollapsibleCard>
      )}

      {/* 월별·연도별 차트는 실적 화면(자산 › 배당 › 월별 배당)에 있다 */}
      {avgProjected > 0 && (
        <div className="card">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">
            배당이 약한 달
          </h3>
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {weakMonths.length > 0 ? weakMonths.join(", ") : "평균의 절반에 못 미치는 달이 없어요"}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            예상 배당금이 월평균의 50% 미만인 달
          </p>
          <Link
            to={portfolioUrl("배당", "월별 배당")}
            className={`inline-flex items-center ${TOUCH_HEIGHT_MIN} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
          >
            월별·연도별 차트 보기
          </Link>
        </div>
      )}

      <CollapsibleCard
        icon={CalendarRange}
        title="월별 균등화 추천"
        isOpen={optimizationOpen}
        onToggle={toggleOptimization}
        collapsedHint="배당이 적은 달을 채워줄 종목 조합을 추천해요"
      >
        <MonthlyOptimizationCard />
      </CollapsibleCard>
    </div>
  );
}
