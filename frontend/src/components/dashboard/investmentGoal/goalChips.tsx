import type { ReactNode } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { fmtKrwShort } from "@/utils/format";
import type { DashboardData } from "@/api/dashboard";

export interface GoalChip {
  key: string;
  label: string;
  shortLabel: string;
  isSet: boolean;
  setupHref: string;
  content: ReactNode;
  barPct?: number;
  barColorClass?: string;
}

function achievementColor(pct: number): string {
  if (pct >= 80) return "text-green-600 dark:text-green-400";
  if (pct >= 50) return "text-blue-600 dark:text-blue-400";
  return "text-gray-500 dark:text-gray-400";
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
          isEven
            ? "text-gray-500 dark:text-gray-400"
            : isAhead
              ? "text-emerald-600 dark:text-emerald-400"
              : "text-amber-600 dark:text-amber-400"
        }`}
      >
        {!isEven && (isAhead ? <TrendingUp size={12} /> : <TrendingDown size={12} />)}
        {isAhead && !isEven ? "+" : ""}
        {gap.toFixed(decimals)}
        {unit}
      </span>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
        {isEven ? "목표 일치" : isAhead ? aheadLabel : behindLabel}
      </p>
    </>
  );
}

function retirementContent(
  retirementTargetYear: number | null | undefined,
  retirementGapYears: number | null,
  expectedGoalYear: number | null,
  yearsUntilRetirement: number | null,
): ReactNode {
  if (retirementGapYears != null) {
    const detail = (
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
        목표 {retirementTargetYear}년 · 예상 {expectedGoalYear}년
      </p>
    );
    if (retirementGapYears === 0) {
      return (
        <>
          <span className="text-sm font-bold text-gray-500 dark:text-gray-400">목표 시점 일치</span>
          {detail}
        </>
      );
    }
    return retirementGapYears > 0 ? (
      <>
        <span className="inline-flex items-center gap-0.5 text-sm font-bold text-emerald-600 dark:text-emerald-400">
          <TrendingUp size={12} />
          {retirementGapYears}년 앞서 달성
        </span>
        {detail}
      </>
    ) : (
      <>
        <span className="inline-flex items-center gap-0.5 text-sm font-bold text-amber-600 dark:text-amber-400">
          <TrendingDown size={12} />
          {Math.abs(retirementGapYears)}년 지연 예상
        </span>
        {detail}
      </>
    );
  }
  if (yearsUntilRetirement != null) {
    return (
      <>
        <span className="text-sm font-bold text-gray-600 dark:text-gray-300">
          {yearsUntilRetirement}년 후
        </span>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">DCA 설정 시 예측</p>
      </>
    );
  }
  return null;
}

interface GoalChipsInput {
  data: DashboardData | undefined;
  expectedGoalYear: number | null;
}

interface GoalChipsResult {
  chips: GoalChip[];
  /** 모바일에서 기본 노출할 "가장 뒤처진 목표" — 모두 순항이면 null */
  laggingKey: string | null;
  hasDepositGoal: boolean;
  hasAssetGoal: boolean;
  hasDividendGoal: boolean;
  hasReturnGoal: boolean;
  hasRetirementGoal: boolean;
}

export function buildGoalChips({ data, expectedGoalYear }: GoalChipsInput): GoalChipsResult {
  const hasDepositGoal = data?.annual_deposit_goal != null && data.deposit_achievement_pct != null;
  const hasAssetGoal = data?.goal_amount != null && data.goal_achievement_pct != null;
  const hasDividendGoal =
    data?.annual_dividend_goal != null && data.dividend_goal_achievement_pct != null;
  const actualReturnPct =
    data?.xirr_pct ?? data?.annual_return_pct ?? data?.cumulative_return_pct ?? null;
  const returnSourceLabel =
    data?.xirr_pct != null
      ? "XIRR"
      : data?.annual_return_pct != null
        ? "연환산"
        : "누적, 추적 90일 미만";
  const goalReturnPct = data?.goal_annual_return_pct ?? null;
  const hasReturnGoal = goalReturnPct != null;
  const returnGapPct = data?.return_goal_gap_pct ?? null;
  // 판정과 값을 한 번에 좁혀 아래에서 `!` 없이 쓴다
  const returnGap =
    goalReturnPct != null && actualReturnPct != null && returnGapPct != null
      ? { goalPct: goalReturnPct, actualPct: actualReturnPct, gapPct: returnGapPct }
      : null;

  const retirementGapYears =
    data?.retirement_target_year != null && expectedGoalYear != null
      ? data.retirement_target_year - expectedGoalYear
      : null;
  const yearsUntilRetirement =
    data?.retirement_target_year != null
      ? data.retirement_target_year - new Date().getFullYear()
      : null;
  const hasRetirementGoal = data?.retirement_target_year != null;

  const chips: GoalChip[] = [
    {
      key: "deposit",
      label: "연간 입금",
      shortLabel: "입금",
      isSet: hasDepositGoal,
      setupHref: "/invest-plan",
      content: (
        <>
          <span
            className={`text-sm font-bold ${achievementColor(data?.deposit_achievement_pct ?? 0)}`}
          >
            {Math.min(data?.deposit_achievement_pct ?? 0, 100).toFixed(1)}%
          </span>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {fmtKrwShort(data?.annual_deposit_current ?? 0)} /{" "}
            {fmtKrwShort(data?.annual_deposit_goal ?? 0)}원
          </p>
        </>
      ),
      barPct: data?.deposit_achievement_pct ?? undefined,
      barColorClass: "bg-blue-500",
    },
    {
      key: "dividend",
      label: "배당 목표",
      shortLabel: "배당",
      isSet: hasDividendGoal,
      setupHref: "/invest-plan?tab=배당 계획",
      content: (
        <>
          <span
            className={`text-sm font-bold ${achievementColor(data?.dividend_goal_achievement_pct ?? 0)}`}
          >
            {Math.min(data?.dividend_goal_achievement_pct ?? 0, 100).toFixed(1)}%
          </span>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {fmtKrwShort(data?.estimated_annual_dividends ?? 0)} /{" "}
            {fmtKrwShort(data?.annual_dividend_goal ?? 0)}원
          </p>
        </>
      ),
      barPct: data?.dividend_goal_achievement_pct ?? undefined,
      barColorClass: "bg-emerald-500",
    },
    {
      key: "return",
      label: "연수익률 목표",
      shortLabel: "연수익률",
      isSet: hasReturnGoal,
      setupHref: "/invest-plan",
      content: returnGap ? (
        <>
          {gapBadge(returnGap.gapPct, {
            unit: "%p",
            aheadLabel: "초과달성",
            behindLabel: "미달",
          })}
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            목표 {returnGap.goalPct}% · 실제 {returnGap.actualPct.toFixed(1)}% ({returnSourceLabel})
          </p>
        </>
      ) : hasReturnGoal ? (
        <>
          <span className="text-sm font-bold text-gray-600 dark:text-gray-300">
            목표 {goalReturnPct}%
          </span>
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">실제 수익률 계산 중</p>
        </>
      ) : null,
    },
    {
      key: "retirement",
      label: "은퇴 목표",
      shortLabel: "은퇴",
      isSet: hasRetirementGoal,
      setupHref: "/invest-plan",
      content: retirementContent(
        data?.retirement_target_year,
        retirementGapYears,
        expectedGoalYear,
        yearsUntilRetirement,
      ),
    },
  ];

  // 모바일은 목표 진행률의 권위 표면이 계획 탭이므로(plans/50 M7) "가장 뒤처진 목표" 1개만 기본 노출한다.
  // 점수가 낮을수록 뒤처짐 — 달성률형은 %, 수익률·은퇴는 미달/지연이면 50으로 본다. 100 이상이면 순항.
  const lagScore: Record<string, number | null> = {
    deposit: hasDepositGoal ? (data?.deposit_achievement_pct ?? null) : null,
    dividend: hasDividendGoal ? (data?.dividend_goal_achievement_pct ?? null) : null,
    return: returnGap ? (returnGap.gapPct < 0 ? 50 : 100) : null,
    retirement: retirementGapYears != null ? (retirementGapYears < 0 ? 50 : 100) : null,
  };
  const laggingKey =
    Object.entries(lagScore)
      .filter((e): e is [string, number] => e[1] != null && e[1] < 100)
      .sort((a, b) => a[1] - b[1])[0]?.[0] ?? null;

  return {
    chips,
    laggingKey,
    hasDepositGoal,
    hasAssetGoal,
    hasDividendGoal,
    hasReturnGoal,
    hasRetirementGoal,
  };
}
