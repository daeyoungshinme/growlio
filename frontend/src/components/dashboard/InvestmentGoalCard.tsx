import { Link } from "react-router-dom";
import { Target } from "lucide-react";
import SkeletonCard from "@/components/common/SkeletonCard";
import { useCollapsible } from "@/hooks/useCollapsible";
import type { DashboardData } from "@/api/dashboard";
import type { DCAAnalysisData } from "@/api/invest";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import GoalChipGrid from "./investmentGoal/GoalChipGrid";
import { DesktopDcaOutlook, MobileDcaOutlook } from "./investmentGoal/DcaOutlook";
import { buildGoalChips } from "./investmentGoal/goalChips";

interface Props {
  data: DashboardData | undefined;
  dcaData?: DCAAnalysisData | undefined;
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
        to="/invest-plan"
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
      >
        {linkLabel}
      </Link>
    </div>
  );
}

export default function InvestmentGoalCard({ data, dcaData, isLoading }: Props) {
  const [dcaDetailOpen, toggleDcaDetail] = useCollapsible(false, "growlio:goalCard:dcaDetailOpen");
  const [showAllGoals, toggleShowAllGoals] = useCollapsible(
    false,
    "growlio:goalCard:showAllGoalsMobile",
  );

  if (isLoading) {
    return <SkeletonCard rows={4} />;
  }

  const timeline = dcaData?.goal_timeline;
  const currentProgressPct = timeline?.current_progress_pct ?? data?.goal_achievement_pct;
  const goalAmountDisplay = dcaData?.settings.goal_amount ?? data?.goal_amount;
  const goalGapAmount =
    goalAmountDisplay != null && data != null ? goalAmountDisplay - data.total_assets_krw : null;
  const expectedGoalDateStr =
    timeline?.actual_expected_goal_date ?? timeline?.expected_goal_date ?? null;
  const expectedGoalYear = expectedGoalDateStr ? Number(expectedGoalDateStr.slice(0, 4)) : null;

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
    timeline,
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
        <MobileDcaOutlook
          {...outlook}
          detailOpen={dcaDetailOpen}
          onToggleDetail={toggleDcaDetail}
        />
      </div>

      <DesktopDcaOutlook {...outlook} />
    </div>
  );
}
