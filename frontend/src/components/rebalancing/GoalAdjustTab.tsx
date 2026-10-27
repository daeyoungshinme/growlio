import { lazy, Suspense, useEffect } from "react";
import type { PortfolioItem } from "@/api/portfolios";
import Tabs from "@/components/common/Tabs";
import SkeletonCard from "@/components/common/SkeletonCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { LABEL_SM, SELECT_SM } from "@/constants/inputStyles";
import { useSelectedPortfolio } from "@/hooks/useSelectedPortfolio";
import { GOAL_MODES, type GoalMode } from "@/utils/rebalancingUrl";

const loadRecommendationCard = () => import("./RecommendationCard");
const loadTacticalAllocationTab = () => import("./TacticalAllocationTab");
const RecommendationCard = lazy(loadRecommendationCard);
const TacticalAllocationTab = lazy(loadTacticalAllocationTab);

const MODE_INTRO: Record<GoalMode, string> = {
  추천: "목표 수익률·연령대·투자 기간에 맞춘 추천 비중을 포트폴리오 목표로 적용해요.",
  전술: "시장 국면(진단 탭 시장 상황의 매크로·차트 추세)에 따라 나스닥·S&P500 목표 비중을 조정하자고 제안해요.",
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
  // 추천·전술이 같은 대상 포트폴리오를 보도록 선택기는 여기 하나만 둔다(plans/64 S2)
  const { portfolios, anchoredIds, selectedId } = useSelectedPortfolio(selectedPortfolioId);

  // 반대쪽 모드 청크를 미리 받아 서브탭 전환 시 청크 대기가 없게 한다
  useEffect(() => {
    void (mode === "추천" ? loadTacticalAllocationTab() : loadRecommendationCard());
  }, [mode]);

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-gray-500 dark:text-gray-400 px-1">
        목표 비중 자체를 바꿀지 제안해요. 적용한 뒤 실제 주문은 포트폴리오 탭에서 해요.
      </p>
      <Tabs tabs={GOAL_MODES} activeTab={mode} onChange={onModeChange} variant="underline" />
      <p className="text-xs text-gray-500 dark:text-gray-400 px-1">{MODE_INTRO[mode]}</p>

      {portfolios.length > 0 && (
        <label className="flex flex-col gap-1 px-1">
          <span className={LABEL_SM}>대상 포트폴리오</span>
          <select
            className={SELECT_SM}
            value={selectedId ?? ""}
            onChange={(e) => onSelectPortfolio(e.target.value)}
          >
            {portfolios.map((p) => (
              <option key={p.id} value={p.id}>
                {anchoredIds.includes(p.id) ? `${p.name} (기준)` : p.name}
              </option>
            ))}
          </select>
          {mode === "추천" && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              단기·중기·장기 추천은 계좌 투자기간이 맞는 포트폴리오에 적용돼요.
            </span>
          )}
        </label>
      )}

      {/* 라우터가 URL 변경을 startTransition으로 감싸서, 이미 그려진 경계는 새 청크 로딩 동안
          이전 화면을 붙잡는다(탭 하이라이트까지 늦게 바뀜). 모드별 key로 새 경계를 만들어 즉시 fallback */}
      <ErrorBoundary variant="section" key={mode}>
        <Suspense fallback={<SkeletonCard />}>
          {mode === "추천" ? (
            <RecommendationCard
              onApplied={onGoToExecution}
              onCreatePortfolio={onCreatePortfolio}
              initialOptionsOpen={initialRecOptionsOpen}
              onOptionsClosed={onRecOptionsClosed}
              selectedPortfolioId={selectedId}
              onSelectPortfolio={onSelectPortfolio}
              showTargetPicker={false}
            />
          ) : (
            <TacticalAllocationTab
              onCreatePortfolio={onCreateEmptyPortfolio}
              selectedPortfolioId={selectedId}
              onSelectPortfolio={onSelectPortfolio}
              onGoToExecution={onGoToExecution}
              showPortfolioPicker={false}
            />
          )}
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
