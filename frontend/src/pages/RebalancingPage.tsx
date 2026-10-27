import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchInflationSummary } from "@/api/economicIndicators";
import { fetchPortfolioRisk } from "@/api/risk";
import { fetchTacticalMarket } from "@/api/tactical";
import { fetchOverallGoalRecommendation } from "@/api/rebalancing";
import type { PortfolioItem } from "@/api/portfolios";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { useRebalancingUrlState } from "@/hooks/useRebalancingUrlState";
import { useSelectedPortfolio } from "@/hooks/useSelectedPortfolio";
import { REBALANCING_TABS, type GoalMode, type RebalancingTab } from "@/utils/rebalancingUrl";
import {
  compositeSignalStatusQuery,
  driftSummaryQuery,
  marketSignalQuery,
  portfoliosQuery,
  settingsQuery,
} from "@/api/queryOptions";

const RebalancingStatusCard = lazy(() => import("../components/dashboard/RebalancingStatusCard"));
const RiskMetricsCard = lazy(() => import("../components/rebalancing/RiskMetricsCard"));
const MarketSignalBanner = lazy(() => import("../components/rebalancing/MarketSignalBanner"));
const InflationIndicatorList = lazy(
  () => import("../components/rebalancing/InflationIndicatorList"),
);
const GoalAdjustTab = lazy(() => import("../components/rebalancing/GoalAdjustTab"));
const PortfolioManageTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioManageTab"),
);
const PortfolioExecutionTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioExecutionTab"),
);
const RebalancingHistoryTab = lazy(() => import("../components/rebalancing/RebalancingHistoryTab"));

// 탭 순서는 핵심 루프(진단 → 포트폴리오에서 분석·실행)를 앞에, 목표 자체를 바꾸는 추천·전술(목표 조정)을
// 뒤에 둔다(plans/64 S1). 탭·URL 정의는 utils/rebalancingUrl.ts.

/** 탭 맨 위 역할 한 줄 */
function TabIntro({ children }: { children: string }) {
  return <p className="text-xs text-gray-500 dark:text-gray-400 px-1">{children}</p>;
}

export default function RebalancingPage() {
  const {
    searchParams,
    tab: localTab,
    mode: goalMode,
    portfolioId,
    navigateTo,
    clearParam,
  } = useRebalancingUrlState();

  const handleTabChange = useCallback((tab: RebalancingTab) => navigateTo({ tab }), [navigateTo]);

  const handleGoalModeChange = useCallback(
    (mode: GoalMode) => navigateTo({ tab: "목표 조정", mode }),
    [navigateTo],
  );

  const handlePortfolioChange = useCallback(
    (id: string) => navigateTo({ portfolioId: id }),
    [navigateTo],
  );

  const handlePortfolioSelectFromDiagnosis = useCallback(
    (id: string, openAlert?: boolean) =>
      navigateTo({ tab: "포트폴리오", portfolioId: id, openAlert: openAlert ? "1" : undefined }),
    [navigateTo],
  );

  // 설정탭 "목표 역산 추천 옵션" 딥링크(openRecOptions=1)로 열린 옵션 모달을 닫으면 파라미터 제거
  const clearOpenRecOptions = useCallback(() => clearParam("openRecOptions"), [clearParam]);

  // 추천 → 새 포트폴리오 생성 prefill. 한 덩어리로 두어 소비 시 이름까지 함께 비운다 — 따로 두면
  // 이름만 남아 다음 "새 포트폴리오"가 이전 추천 이름으로 열렸다(plans/62 B3)
  const [prefill, setPrefill] = useState<{
    items: PortfolioItem[];
    name: string;
    accountIds: string[] | null;
  } | null>(null);
  // 빈 상태 CTA(진단 탭·목표 조정 › 전술) — 탭만 바꾸면 다시 "만들기"를 찾아 눌러야 해서 편집기까지 바로 연다.
  // 빈 prefill이면 PortfolioManageTab이 신규 생성 모드로 편집기를 연다(plans/63 P3-5)
  const openNewPortfolioEditor = useCallback(() => {
    setPrefill({ items: [], name: "", accountIds: null });
    handleTabChange("포트폴리오");
  }, [handleTabChange]);
  // URL이 비어 있으면 기준 포트폴리오를 기본으로 — 예전엔 아무것도 선택되지 않아 분석·실행 영역이 숨겨졌다.
  // 기본값은 URL에 쓰지 않고 파생만 한다(plans/64 S3)
  const { selectedId: effectivePortfolioId } = useSelectedPortfolio(portfolioId);

  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, REBALANCING_TABS, localTab, handleTabChange);

  const executionRef = useRef<HTMLDivElement>(null);
  const scrolledForPortfolioIdRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!portfolioId || localTab !== "포트폴리오") return;
    if (scrolledForPortfolioIdRef.current === portfolioId) return;
    scrolledForPortfolioIdRef.current = portfolioId;
    const timer = setTimeout(() => {
      executionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
    return () => clearTimeout(timer);
  }, [portfolioId, localTab]);

  const { data: signal, isError: signalError } = useQuery(marketSignalQuery);

  const { data: riskMetrics } = useQuery({
    queryKey: QUERY_KEYS.portfolioRisk,
    queryFn: () => fetchPortfolioRisk(),
    staleTime: STALE_TIME.LONG,
    enabled: localTab === "진단",
  });

  // RebalancingStatusCard/PortfolioManageTab이 동일 queryKey(portfolios)로 조회한다 — 여기서 같은
  // 렌더 틱에 미리 발화해두면(캐시 dedup) 진단탭 첫 방문 시 카드가 즉시 "포트폴리오 0개" 여부를
  // 판별해 CTA/카드를 스태거링 없이 렌더한다.
  useQuery({
    ...portfoliosQuery,
    enabled: localTab === "진단",
  });

  // 시장 상황 카드의 차트 추세(QQQ·SPY) — 포트폴리오 무관, 서버 6h 캐시. 실패해도 매크로 영역은 그대로
  const { data: tacticalMarket } = useQuery({
    queryKey: QUERY_KEYS.tacticalMarket,
    queryFn: fetchTacticalMarket,
    staleTime: STALE_TIME.LONG,
    enabled: localTab === "진단",
  });

  const { data: inflationSummary } = useQuery({
    queryKey: QUERY_KEYS.inflationSummary,
    queryFn: fetchInflationSummary,
    staleTime: STALE_TIME.LONG,
    enabled: localTab === "진단",
  });

  // MarketSignalBanner(useCompositeSignalToggle)는 signal 로딩 후에야 마운트되므로, 같은
  // queryKey로 여기서 signal과 병렬로 미리 조회해두면 배너 마운트 시 캐시로 즉시 표시된다.
  useQuery({
    ...compositeSignalStatusQuery,
    enabled: localTab === "진단",
  });

  // RebalancingStatusCard도 동일 queryKey로 driftSummary를 조회한다 — 여기서 다른 쿼리들과 같은
  // 렌더 틱에 미리 발화해두면(React Query 캐시 dedup) 콜드 캐시에서도 스태거링 없이 동시에 조회되어
  // 콜드 캐시 경쟁 창을 줄인다.
  useQuery({
    ...driftSummaryQuery,
    enabled: localTab === "진단",
  });

  // 목표 조정 › 추천의 전체 추천은 콜드 계산이 무겁다 — RecommendationCard는 lazy 청크 2단계
  // (GoalAdjustTab → RecommendationCard)를 받은 뒤에야 마운트되므로, 여기서 같은 queryKey로 먼저
  // 발화해 청크 로딩과 병렬로 돌린다(옵션은 RecommendationCard와 동일하게 유지).
  const goalRecommendationTab = localTab === "목표 조정" && goalMode === "추천";
  useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    staleTime: STALE_TIME.LONG,
    gcTime: STALE_TIME.DAY,
    enabled: goalRecommendationTab,
  });
  useQuery({
    ...settingsQuery,
    enabled: goalRecommendationTab,
  });

  return (
    <div className="flex flex-col min-h-full gap-4">
      <h1 className="sr-only">리밸런싱</h1>
      <div className="px-1">
        <Tabs
          tabs={REBALANCING_TABS}
          activeTab={localTab}
          onChange={handleTabChange}
          variant="pill"
        />
      </div>

      <div ref={tabContentRef} className="flex-1 flex flex-col gap-4">
        {/* ── 진단 탭: 전체 포트폴리오 드리프트 현황 + 시장신호 ── */}
        {localTab === "진단" && (
          <>
            <TabIntro>
              목표 비중 이탈·시장 상황·내 포트폴리오 위험을 점검해요. 목표 비중은 바꾸지 않아요.
            </TabIntro>
            <ErrorBoundary variant="section">
              <Suspense fallback={<SkeletonCard />}>
                <RebalancingStatusCard
                  marketSignal={signal ?? undefined}
                  onPortfolioSelect={handlePortfolioSelectFromDiagnosis}
                  emptyStateCta={openNewPortfolioEditor}
                />
              </Suspense>
            </ErrorBoundary>
            {signal && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={1} />}>
                  <MarketSignalBanner
                    signal={signal}
                    inflation={inflationSummary}
                    technicals={tacticalMarket?.technicals}
                    onOpenTactical={() => handleGoalModeChange("전술")}
                  />
                </Suspense>
              </ErrorBoundary>
            )}
            {/* 물가 지표는 별도 조회라 시장신호 조회가 실패해도 단독 카드로 보여준다(plans/39 N7) */}
            {!signal && signalError && inflationSummary && inflationSummary.length > 0 && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={1} />}>
                  <div className="card">
                    <InflationIndicatorList data={inflationSummary} />
                  </div>
                </Suspense>
              </ErrorBoundary>
            )}
            {riskMetrics && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard />}>
                  <RiskMetricsCard metrics={riskMetrics} />
                </Suspense>
              </ErrorBoundary>
            )}
          </>
        )}

        {/* ── 포트폴리오 탭: 목록 관리 + 분석/실행 ── */}
        {localTab === "포트폴리오" && (
          <>
            <Suspense fallback={<SkeletonCard />}>
              <PortfolioManageTab
                selectedPortfolioId={effectivePortfolioId}
                onAnalyze={handlePortfolioChange}
                prefillItems={prefill?.items ?? null}
                prefillName={prefill?.name ?? ""}
                prefillAccountIds={prefill?.accountIds ?? null}
                onPrefillConsumed={() => setPrefill(null)}
              />
            </Suspense>
            {effectivePortfolioId && (
              <div ref={executionRef}>
                <div className="flex items-center gap-3 px-1">
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                  <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    분석 및 실행
                  </span>
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                </div>
                <Suspense fallback={<SkeletonCard />}>
                  <PortfolioExecutionTab
                    portfolioId={effectivePortfolioId}
                    scrollToResult={portfolioId !== undefined}
                  />
                </Suspense>
              </div>
            )}
          </>
        )}

        {/* ── 목표 조정 탭: 추천·전술 — 목표 비중 자체를 바꾸고, 실행은 포트폴리오 탭으로 ── */}
        {localTab === "목표 조정" && (
          <Suspense fallback={<SkeletonCard />}>
            <GoalAdjustTab
              mode={goalMode}
              onModeChange={handleGoalModeChange}
              selectedPortfolioId={portfolioId}
              onSelectPortfolio={handlePortfolioChange}
              onGoToExecution={(id) => handlePortfolioSelectFromDiagnosis(id)}
              onCreatePortfolio={(items, name, accountIds) => {
                setPrefill({ items, name, accountIds: accountIds ?? null });
                // 포트폴리오 편집기는 포트폴리오 탭(PortfolioManageTab)이 prefill을 소비해 연다
                handleTabChange("포트폴리오");
              }}
              onCreateEmptyPortfolio={openNewPortfolioEditor}
              initialRecOptionsOpen={searchParams.get("openRecOptions") === "1"}
              onRecOptionsClosed={clearOpenRecOptions}
            />
          </Suspense>
        )}

        {/* ── 이력 탭 ── */}
        {localTab === "이력" && (
          <Suspense fallback={<SkeletonCard />}>
            <RebalancingHistoryTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
