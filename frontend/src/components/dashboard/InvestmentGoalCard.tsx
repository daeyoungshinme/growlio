import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Target, TrendingDown, TrendingUp } from "lucide-react";
import { fmtKrw, fmtMonth } from "@/utils/format";
import type { DashboardData } from "@/api/dashboard";
import type { DCAAnalysisData } from "@/api/invest";

function achievementColor(pct: number): string {
  if (pct >= 80) return "text-green-600 dark:text-green-400";
  if (pct >= 50) return "text-blue-600 dark:text-blue-400";
  return "text-gray-500 dark:text-gray-400";
}

interface Props {
  data: DashboardData | undefined;
  dcaData?: DCAAnalysisData | undefined;
  isLoading?: boolean;
}

interface GapBadgeOptions {
  unit: string;
  decimals?: number;
  aheadLabel: string;
  behindLabel: string;
}

function gapBadge(gap: number, { unit, decimals = 1, aheadLabel, behindLabel }: GapBadgeOptions) {
  const isAhead = gap > 0;
  const isEven = gap === 0;
  return (
    <>
      <span
        className={`inline-flex items-center gap-0.5 text-sm font-bold ${
          isEven ? "text-gray-500 dark:text-gray-400" : isAhead ? "text-red-500" : "text-blue-500"
        }`}
      >
        {!isEven && (isAhead ? <TrendingUp size={12} /> : <TrendingDown size={12} />)}
        {isAhead && !isEven ? "+" : ""}
        {gap.toFixed(decimals)}
        {unit}
      </span>
      <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
        {isEven ? "목표 일치" : isAhead ? aheadLabel : behindLabel}
      </p>
    </>
  );
}

export default function InvestmentGoalCard({ data, dcaData, isLoading }: Props) {
  const timeline = dcaData?.goal_timeline;
  const currentProgressPct = timeline?.current_progress_pct ?? data?.goal_achievement_pct;
  const goalAmountDisplay = dcaData?.settings.goal_amount ?? data?.goal_amount;
  const hasDepositGoal = data?.annual_deposit_goal != null && data.deposit_achievement_pct != null;
  const hasAssetGoal = data?.goal_amount != null && data.goal_achievement_pct != null;
  const hasDividendGoal =
    data?.annual_dividend_goal != null && data.dividend_goal_achievement_pct != null;
  const actualReturnPct = data?.xirr_pct ?? data?.annual_return_pct ?? null;
  const hasReturnGoal = data?.goal_annual_return_pct != null;
  const canShowReturnGap =
    hasReturnGoal && actualReturnPct != null && data?.return_goal_gap_pct != null;

  const expectedGoalDateStr =
    timeline?.actual_expected_goal_date ?? timeline?.expected_goal_date ?? null;
  const expectedGoalYear = expectedGoalDateStr ? Number(expectedGoalDateStr.slice(0, 4)) : null;
  const retirementGapYears =
    data?.retirement_target_year != null && expectedGoalYear != null
      ? data.retirement_target_year - expectedGoalYear
      : null;
  const yearsUntilRetirement =
    data?.retirement_target_year != null
      ? data.retirement_target_year - new Date().getFullYear()
      : null;
  const hasRetirementGoal = data?.retirement_target_year != null;

  const goalChips: {
    key: string;
    label: string;
    isSet: boolean;
    content: ReactNode;
    barPct?: number;
    barColorClass?: string;
  }[] = [
    {
      key: "deposit",
      label: "연간 입금",
      isSet: hasDepositGoal,
      content: (
        <span
          className={`text-sm font-bold ${achievementColor(data?.deposit_achievement_pct ?? 0)}`}
        >
          {Math.min(data?.deposit_achievement_pct ?? 0, 100).toFixed(1)}%
        </span>
      ),
      barPct: data?.deposit_achievement_pct ?? undefined,
      barColorClass: "bg-blue-500",
    },
    {
      key: "asset",
      label: "자산 목표",
      isSet: hasAssetGoal,
      content: (
        <span className={`text-sm font-bold ${achievementColor(data?.goal_achievement_pct ?? 0)}`}>
          {Math.min(data?.goal_achievement_pct ?? 0, 100).toFixed(1)}%
        </span>
      ),
      barPct: data?.goal_achievement_pct ?? undefined,
      barColorClass: "bg-blue-500",
    },
    {
      key: "dividend",
      label: "배당 목표",
      isSet: hasDividendGoal,
      content: (
        <span
          className={`text-sm font-bold ${achievementColor(data?.dividend_goal_achievement_pct ?? 0)}`}
        >
          {Math.min(data?.dividend_goal_achievement_pct ?? 0, 100).toFixed(1)}%
        </span>
      ),
      barPct: data?.dividend_goal_achievement_pct ?? undefined,
      barColorClass: "bg-emerald-500",
    },
    {
      key: "return",
      label: "연수익률 목표",
      isSet: hasReturnGoal,
      content: canShowReturnGap ? (
        gapBadge(data!.return_goal_gap_pct!, {
          unit: "%p",
          aheadLabel: "초과달성",
          behindLabel: "미달",
        })
      ) : hasReturnGoal ? (
        <>
          <span className="text-sm font-bold text-gray-600 dark:text-gray-300">
            목표 {data!.goal_annual_return_pct}%
          </span>
          <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">실제 수익률 계산 중</p>
        </>
      ) : null,
    },
    {
      key: "retirement",
      label: "은퇴 목표",
      isSet: hasRetirementGoal,
      content:
        retirementGapYears != null ? (
          retirementGapYears === 0 ? (
            <span className="text-sm font-bold text-gray-500 dark:text-gray-400">
              목표 시점 일치
            </span>
          ) : retirementGapYears > 0 ? (
            <>
              <span className="inline-flex items-center gap-0.5 text-sm font-bold text-red-500">
                <TrendingUp size={12} />
                {retirementGapYears}년 앞서 달성
              </span>
              <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
                은퇴 전 목표 도달
              </p>
            </>
          ) : (
            <>
              <span className="inline-flex items-center gap-0.5 text-sm font-bold text-blue-500">
                <TrendingDown size={12} />
                {Math.abs(retirementGapYears)}년 지연 예상
              </span>
              <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
                은퇴 후 도달 예상
              </p>
            </>
          )
        ) : yearsUntilRetirement != null ? (
          <>
            <span className="text-sm font-bold text-gray-600 dark:text-gray-300">
              {yearsUntilRetirement}년 후
            </span>
            <p className="text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">DCA 설정 시 예측</p>
          </>
        ) : null,
    },
  ];

  if (
    !isLoading &&
    !hasDepositGoal &&
    !hasAssetGoal &&
    !hasDividendGoal &&
    !hasReturnGoal &&
    !hasRetirementGoal
  ) {
    return (
      <div className="card">
        <div className="flex items-center justify-between mb-2 sm:mb-4">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
            <Target size={16} className="text-blue-500" />
            투자 목표
          </h2>
          <Link
            to="/invest-plan"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            목표 설정
          </Link>
        </div>
        <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-4">
          투자 목표가 설정되지 않았습니다 — 계획 탭에서 입력해주세요
        </p>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
          <Target size={16} className="text-blue-500" />
          투자 목표
        </h2>
        <Link
          to="/invest-plan"
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          자세히 보기
        </Link>
      </div>

      {/* 목표 항목 — 가로 스크롤 칩 한 줄 (항목 수가 늘어도 세로로 자라지 않음) */}
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        {goalChips.map((chip) => (
          <div
            key={chip.key}
            className="min-w-[104px] flex-shrink-0 rounded-xl border border-gray-100 dark:border-gray-700 p-2.5"
          >
            <p className="text-[11px] text-gray-500 dark:text-gray-400 mb-1 truncate">
              {chip.label}
            </p>
            {chip.isSet ? (
              <>
                {chip.content}
                {chip.barPct != null && (
                  <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1.5">
                    <div
                      className={`h-full rounded-full ${chip.barColorClass}`}
                      style={{ width: `${Math.min(Math.max(chip.barPct, 0), 100)}%` }}
                    />
                  </div>
                )}
              </>
            ) : (
              <p className="text-xs text-gray-300 dark:text-gray-600">미설정</p>
            )}
          </div>
        ))}
      </div>

      {/* 모바일 DCA 달성 전망 — 2행 부각 */}
      <div className="sm:hidden border-t border-gray-100 dark:border-gray-700 pt-1.5 mt-1.5">
        {currentProgressPct != null || timeline ? (
          <>
            <div className="flex items-end justify-between">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">전체 진행율</p>
                <p className="text-base font-bold text-gray-900 dark:text-gray-50">
                  {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
                </p>
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">실제 달성 예상</p>
                <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                  {timeline?.actual_expected_goal_date
                    ? fmtMonth(timeline.actual_expected_goal_date)
                    : timeline?.expected_goal_date
                      ? fmtMonth(timeline.expected_goal_date)
                      : "—"}
                </p>
              </div>
            </div>
            <div className="flex items-center justify-between mt-1">
              {timeline?.lead_lag_months != null && timeline.lead_lag_months !== 0 ? (
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                    timeline.lead_lag_months > 0
                      ? "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400"
                      : "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400"
                  }`}
                >
                  {timeline.lead_lag_months > 0 ? (
                    <>
                      <TrendingUp size={10} />
                      {timeline.lead_lag_months}개월 앞서
                    </>
                  ) : (
                    <>
                      <TrendingDown size={10} />
                      {Math.abs(timeline.lead_lag_months)}개월 지연
                    </>
                  )}
                </span>
              ) : (
                <span />
              )}
              {timeline?.expected_goal_date &&
                timeline?.lead_lag_months != null &&
                timeline.lead_lag_months !== 0 && (
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    계획: {fmtMonth(timeline.expected_goal_date)}
                  </span>
                )}
            </div>
            <div className="h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden mt-1">
              <div
                className="h-full bg-blue-500 rounded-full transition-all"
                style={{ width: `${Math.min(currentProgressPct ?? 0, 100)}%` }}
              />
            </div>
          </>
        ) : (
          <Link
            to="/invest-plan"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            DCA 투자 계획 설정하기 →
          </Link>
        )}
      </div>

      {/* 데스크탑 DCA 달성 전망 — 부각 PRIMARY */}
      {currentProgressPct != null || timeline ? (
        <div className="hidden sm:block border-t border-gray-100 dark:border-gray-700 pt-2 mt-2 space-y-2">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">
                전체 진행율
              </p>
              <p className="text-lg font-bold text-gray-900 dark:text-gray-50">
                {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
              </p>
              {goalAmountDisplay != null && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  목표 {fmtKrw(goalAmountDisplay)}
                </p>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">
                실제 달성 예상
              </p>
              <p className="text-base font-semibold text-blue-600 dark:text-blue-400">
                {timeline?.actual_expected_goal_date
                  ? fmtMonth(timeline.actual_expected_goal_date)
                  : timeline?.expected_goal_date
                    ? fmtMonth(timeline.expected_goal_date)
                    : "—"}
              </p>
              {timeline?.months_to_goal != null && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  약 {timeline.months_to_goal}개월 후
                </p>
              )}
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">
                계획 대비
              </p>
              {timeline?.lead_lag_months == null ? (
                <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">—</p>
              ) : timeline.lead_lag_months > 0 ? (
                <div className="mt-0.5 flex flex-col gap-1">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400 w-fit">
                    <TrendingUp size={11} />
                    {timeline.lead_lag_months}개월 앞서
                  </span>
                  {timeline.expected_goal_date && (
                    <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                      계획 기준: {fmtMonth(timeline.expected_goal_date)}
                    </span>
                  )}
                </div>
              ) : timeline.lead_lag_months < 0 ? (
                <div className="mt-0.5 flex flex-col gap-1">
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400 w-fit">
                    <TrendingDown size={11} />
                    {Math.abs(timeline.lead_lag_months)}개월 지연
                  </span>
                  {timeline.expected_goal_date && (
                    <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                      계획 기준: {fmtMonth(timeline.expected_goal_date)}
                    </span>
                  )}
                </div>
              ) : (
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1">
                  계획과 일치
                </p>
              )}
            </div>
          </div>
          <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all"
              style={{ width: `${Math.min(currentProgressPct ?? 0, 100)}%` }}
            />
          </div>
        </div>
      ) : (
        <div className="hidden sm:block border-t border-gray-100 dark:border-gray-700 pt-4 mt-3">
          <Link
            to="/invest-plan"
            className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            DCA 투자 계획 설정하기 <ArrowRight size={12} />
          </Link>
        </div>
      )}
    </div>
  );
}
