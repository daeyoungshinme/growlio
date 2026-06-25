import { Link } from "react-router-dom";
import { ArrowRight, Target, TrendingDown, TrendingUp } from "lucide-react";
import { fmtKrw, fmtMonth } from "@/utils/format";
import type { DashboardData } from "@/api/dashboard";
import type { DCAAnalysisData } from "@/api/invest";

interface Props {
  data: DashboardData | undefined;
  dcaData?: DCAAnalysisData | undefined;
  isLoading?: boolean;
}

export default function InvestmentGoalCard({ data, dcaData, isLoading }: Props) {
  const timeline = dcaData?.goal_timeline;
  const currentProgressPct = timeline?.current_progress_pct ?? data?.goal_achievement_pct;
  const goalAmountDisplay = dcaData?.settings.goal_amount ?? data?.goal_amount;
  const hasDepositGoal = data?.annual_deposit_goal != null && data.deposit_achievement_pct != null;
  const hasAssetGoal = data?.goal_amount != null && data.goal_achievement_pct != null;

  if (!isLoading && !hasDepositGoal && !hasAssetGoal) {
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

      {/* 모바일 컴팩트 목표 2열 */}
      <div className="sm:hidden flex gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">연간 입금</p>
          {hasDepositGoal ? (
            <>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                {Math.min(data!.deposit_achievement_pct!, 100).toFixed(1)}%
                <span className="text-xs font-normal text-gray-400 dark:text-gray-500 ml-1">달성</span>
              </p>
              <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(data!.deposit_achievement_pct!, 100)}%` }}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500">미설정</p>
          )}
        </div>

        <div className="w-px bg-gray-100 dark:bg-gray-700 self-stretch" />

        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">자산 목표</p>
          {hasAssetGoal ? (
            <>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                {Math.min(data!.goal_achievement_pct!, 100).toFixed(1)}%
                <span className="text-xs font-normal text-gray-400 dark:text-gray-500 ml-1">달성</span>
              </p>
              <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(data!.goal_achievement_pct!, 100)}%` }}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500">미설정</p>
          )}
        </div>
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
                    <><TrendingUp size={10} />{timeline.lead_lag_months}개월 앞서</>
                  ) : (
                    <><TrendingDown size={10} />{Math.abs(timeline.lead_lag_months)}개월 지연</>
                  )}
                </span>
              ) : (
                <span />
              )}
              {timeline?.expected_goal_date && timeline?.lead_lag_months != null && timeline.lead_lag_months !== 0 && (
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  계획: {fmtMonth(timeline.expected_goal_date)}
                </span>
              )}
            </div>
            <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden mt-1">
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

      {/* 데스크탑 목표 2열 — compact secondary */}
      <div className="hidden sm:grid sm:grid-cols-2 sm:gap-3">
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>연간 입금 달성률</span>
            {hasDepositGoal && (
              <span className="font-medium text-gray-700 dark:text-gray-300">
                목표 {fmtKrw(data!.annual_deposit_goal!)}
              </span>
            )}
          </div>
          {hasDepositGoal ? (
            <>
              <div className="flex items-end gap-1">
                <span className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                  {Math.min(data!.deposit_achievement_pct!, 100).toFixed(1)}%
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">달성</span>
              </div>
              <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(data!.deposit_achievement_pct!, 100)}%` }}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500">미설정</p>
          )}
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
            <span>자산 목표 달성률</span>
            {hasAssetGoal && (
              <span className="font-medium text-gray-700 dark:text-gray-300">
                목표 {fmtKrw(data!.goal_amount!)}
              </span>
            )}
          </div>
          {hasAssetGoal ? (
            <>
              <div className="flex items-end gap-1">
                <span className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                  {Math.min(data!.goal_achievement_pct!, 100).toFixed(1)}%
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 mb-0.5">달성</span>
                {data!.retirement_target_year != null && (
                  <span className="text-xs text-gray-400 dark:text-gray-500 mb-0.5 ml-1">
                    ({data!.retirement_target_year}년 목표)
                  </span>
                )}
              </div>
              <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-500"
                  style={{ width: `${Math.min(data!.goal_achievement_pct!, 100)}%` }}
                />
              </div>
            </>
          ) : (
            <p className="text-sm text-gray-400 dark:text-gray-500">미설정</p>
          )}
        </div>
      </div>

      {/* 데스크탑 DCA 달성 전망 — 부각 PRIMARY */}
      {currentProgressPct != null || timeline ? (
        <div className="hidden sm:block border-t border-gray-100 dark:border-gray-700 pt-2 mt-2 space-y-2">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">전체 진행율</p>
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
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">실제 달성 예상</p>
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
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">계획 대비</p>
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
