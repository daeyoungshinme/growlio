import { Link } from "react-router-dom";
import { Target } from "lucide-react";
import SkeletonCard from "@/components/common/SkeletonCard";
import { useCollapsible } from "@/hooks/useCollapsible";
import type { DashboardData } from "@/api/dashboard";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import GoalChipGrid from "./investmentGoal/GoalChipGrid";
import { DcaOutlook } from "./investmentGoal/DcaOutlook";
import { buildGoalChips } from "./investmentGoal/goalChips";
import { investPlanUrl } from "@/utils/tabUrl";

interface Props {
  data: DashboardData | undefined;
  isLoading?: boolean;
}

function CardHeader({ linkLabel, className }: { linkLabel: string; className: string }) {
  return (
    <div className={`flex items-center justify-between ${className}`}>
      <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
        <div className="p-1.5 bg-violet-50 dark:bg-violet-950 rounded-lg shrink-0">
          <Target size={16} className="text-violet-600 dark:text-violet-400" />
        </div>
        투자 목표 달성 현황
      </h2>
      <Link
        to={investPlanUrl("적립 계획")}
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
      >
        {linkLabel}
      </Link>
    </div>
  );
}

export default function InvestmentGoalCard({ data, isLoading }: Props) {
  const [showAllGoals, toggleShowAllGoals] = useCollapsible(
    false,
    "growlio:goalCard:showAllGoalsMobile",
  );

  if (isLoading) {
    return <SkeletonCard rows={4} />;
  }

  // 진행률·달성 예상월은 대시보드 응답 하나로 — 적립 분석 전체를 따로 받지 않는다(plans/151 B1).
  // 진행률은 적립 분석 goal_timeline과 같은 식(부동산 제외 투자자산 ÷ 목표)이다
  const currentProgressPct = data?.goal_achievement_pct;
  const goalAmountDisplay = data?.goal_amount;
  const expectedGoalMonth = data?.goal_expected_month ?? null;
  // 진행률과 같은 기준(부동산 제외) — 총자산으로 빼면 진행률 60%인데 "달성"으로 보일 수 있다
  const investableAssets = data?.investable_assets_krw;
  const goalGapAmount =
    goalAmountDisplay != null && investableAssets != null
      ? goalAmountDisplay - investableAssets
      : null;
  const expectedGoalYear = expectedGoalMonth ? Number(expectedGoalMonth.slice(0, 4)) : null;

  const goals = buildGoalChips({ data, expectedGoalYear });

  if (
    !goals.hasDepositGoal &&
    !goals.hasAssetGoal &&
    !goals.hasDividendGoal &&
    !goals.hasReturnGoal &&
    !goals.hasRetirementGoal
  ) {
    return (
      <div className="card">
        <CardHeader linkLabel="목표 설정" className="mb-2 sm:mb-4" />
        <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-4">
          투자 목표가 설정되지 않았습니다 — 계획 탭에서 입력해주세요
        </p>
      </div>
    );
  }

  const outlook = {
    expectedGoalMonth,
    currentProgressPct,
    goalAmountDisplay,
    goalGapAmount,
    hasData: data != null,
  };

  return (
    <div className="card">
      <CardHeader linkLabel="자세히 보기" className="mb-2" />

      <div className="flex flex-col">
        <GoalChipGrid
          chips={goals.chips}
          laggingKey={goals.laggingKey}
          showAll={showAllGoals}
          onToggleShowAll={toggleShowAllGoals}
        />
        <DcaOutlook {...outlook} />
      </div>
    </div>
  );
}
