import { lazy, Suspense } from "react";
import type { PortfolioItem } from "@/api/portfolios";
import Tabs from "@/components/common/Tabs";
import SkeletonCard from "@/components/common/SkeletonCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { GOAL_MODES, type GoalMode } from "@/utils/rebalancingUrl";

const RecommendationCard = lazy(() => import("./RecommendationCard"));
const TacticalAllocationTab = lazy(() => import("./TacticalAllocationTab"));

const MODE_INTRO: Record<GoalMode, string> = {
  추천: "목표 수익률·연령대·투자 기간에 맞춘 추천 비중을 포트폴리오 목표로 적용해요.",
  전술: "시장 국면(매크로+차트 추세)에 따라 QQQ·SPY 목표 비중을 조정하자고 제안해요.",
};

interface Props {
  mode: GoalMode;
  onModeChange: (mode: GoalMode) => void;
  selectedPortfolioId?: string;
  onSelectPortfolio: (id: string) => void;
  /** 적용 후 실행 — 포트폴리오 탭의 분석·실행으로 이동 */
  onGoToExecution: (id: string) => void;
  onCreatePortfolio: (items: PortfolioItem[], name: string, accountIds?: string[]) => void;
  onCreateEmptyPortfolio: () => void;
  initialRecOptionsOpen: boolean;
  onRecOptionsClosed: () => void;
}

/**
 * 리밸런싱 › 목표 조정 탭 — 추천과 전술은 둘 다 "목표 비중 자체를 바꾸는 제안"이라 한 탭에
 * 모았다(plans/64 S2). 진단·포트폴리오 탭은 정해 둔 목표 대비 이탈을 보고 실행하는 쪽.
 */
export default function GoalAdjustTab({
  mode,
  onModeChange,
  selectedPortfolioId,
  onSelectPortfolio,
  onGoToExecution,
  onCreatePortfolio,
  onCreateEmptyPortfolio,
  initialRecOptionsOpen,
  onRecOptionsClosed,
}: Props) {
  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 px-1">
        목표 비중 자체를 바꿀지 제안해요. 적용한 뒤 실제 주문은 포트폴리오 탭에서 해요.
      </p>
      <Tabs tabs={GOAL_MODES} activeTab={mode} onChange={onModeChange} variant="underline" />
      <p className="text-xs text-gray-500 dark:text-gray-400 px-1">{MODE_INTRO[mode]}</p>

      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard />}>
          {mode === "추천" ? (
            <RecommendationCard
              onApplied={onGoToExecution}
              onCreatePortfolio={onCreatePortfolio}
              initialOptionsOpen={initialRecOptionsOpen}
              onOptionsClosed={onRecOptionsClosed}
              selectedPortfolioId={selectedPortfolioId}
              onSelectPortfolio={onSelectPortfolio}
            />
          ) : (
            <TacticalAllocationTab
              onCreatePortfolio={onCreateEmptyPortfolio}
              selectedPortfolioId={selectedPortfolioId}
              onSelectPortfolio={onSelectPortfolio}
              onGoToExecution={onGoToExecution}
            />
          )}
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
