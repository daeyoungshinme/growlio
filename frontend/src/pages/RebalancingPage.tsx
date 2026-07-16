import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchMarketSignal } from "@/api/marketSignals";
import { fetchInflationSummary } from "@/api/economicIndicators";
import { fetchPortfolioRisk } from "@/api/risk";
import { fetchCompositeSignalStatus, fetchDriftSummary } from "@/api/rebalancing";
import type { PortfolioItem } from "@/api/portfolios";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import DiagnosisSummaryHeader from "@/components/rebalancing/DiagnosisSummaryHeader";

const RebalancingStatusCard = lazy(() => import("../components/dashboard/RebalancingStatusCard"));
const RiskMetricsCard = lazy(() => import("../components/rebalancing/RiskMetricsCard"));
const MarketSignalBanner = lazy(() => import("../components/rebalancing/MarketSignalBanner"));
const InflationSummaryCard = lazy(() => import("../components/rebalancing/InflationSummaryCard"));
const RecommendationCard = lazy(() => import("../components/rebalancing/RecommendationCard"));
const PortfolioManageTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioManageTab"),
);
const PortfolioExecutionTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioExecutionTab"),
);
const RebalancingHistoryTab = lazy(() => import("../components/rebalancing/RebalancingHistoryTab"));
const BacktestTab = lazy(() => import("../components/rebalancing/BacktestTab"));

const REBALANCING_PAGE_TABS = ["진단", "포트폴리오", "백테스팅", "이력"] as const;
type RebalancingPageTab = (typeof REBALANCING_PAGE_TABS)[number];

export default function RebalancingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const portfolioId = searchParams.get("portfolioId") ?? undefined;
  const rawTab = searchParams.get("rtab");
  const [localTab, setLocalTab] = useState<RebalancingPageTab>(
    REBALANCING_PAGE_TABS.includes(rawTab as RebalancingPageTab)
      ? (rawTab as RebalancingPageTab)
      : "진단",
  );

  const handleTabChange = useCallback(
    (tab: RebalancingPageTab) => {
      setLocalTab(tab);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("rtab", tab);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handlePortfolioChange = useCallback(
    (id: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("portfolioId", id);
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const handlePortfolioSelectFromDiagnosis = useCallback(
    (id: string, openAlert?: boolean, openExecution?: boolean) => {
      setLocalTab("포트폴리오");
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("portfolioId", id);
          next.set("rtab", "포트폴리오");
          if (openAlert) {
            next.set("openAlert", "1");
          }
          if (openExecution) {
            next.set("openExecution", "1");
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const [prefillItems, setPrefillItems] = useState<PortfolioItem[] | null>(null);
  const [prefillName, setPrefillName] = useState("");
  const [prefillAccountIds, setPrefillAccountIds] = useState<string[] | null>(null);

  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, REBALANCING_PAGE_TABS, localTab, handleTabChange);

  const executionRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!portfolioId || localTab !== "포트폴리오") return;
    const timer = setTimeout(() => {
      executionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
    return () => clearTimeout(timer);
  }, [portfolioId, localTab]);

  const { data: signal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.MEDIUM,
  });

  const { data: riskMetrics } = useQuery({
    queryKey: QUERY_KEYS.portfolioRisk(),
    queryFn: () => fetchPortfolioRisk(),
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
    queryKey: QUERY_KEYS.compositeSignalStatus,
    queryFn: fetchCompositeSignalStatus,
    staleTime: STALE_TIME.LONG,
    enabled: localTab === "진단",
  });

  // RebalancingStatusCard도 동일 queryKey로 driftSummary를 조회한다 — 여기서 다른 3개 쿼리와
  // 같은 렌더 틱에 미리 발화해두면(React Query 캐시 dedup) 콜드 캐시에서도 스태거링 없이
  // 동시에 조회되어 콜드 캐시 경쟁 창을 줄인다. 또한 이 헤더(DiagnosisSummaryHeader)의
  // 드리프트 개수 계산에도 재사용한다.
  const { data: driftSummaries } = useQuery({
    queryKey: QUERY_KEYS.driftSummary,
    queryFn: fetchDriftSummary,
    staleTime: STALE_TIME.MEDIUM,
    enabled: localTab === "진단",
  });

  return (
    <div className="flex flex-col min-h-full gap-4">
      <div className="px-1">
        <Tabs
          tabs={REBALANCING_PAGE_TABS}
          activeTab={localTab}
          onChange={handleTabChange}
          variant="pill"
        />
      </div>

      <div ref={tabContentRef} className="flex-1 flex flex-col gap-4">
        {/* ── 진단 탭: 전체 포트폴리오 드리프트 현황 + 시장신호 ── */}
        {localTab === "진단" && (
          <>
            <ErrorBoundary variant="section">
              <DiagnosisSummaryHeader
                driftSummaries={driftSummaries}
                marketSignal={signal}
                riskMetrics={riskMetrics}
              />
            </ErrorBoundary>
            <ErrorBoundary variant="section">
              <Suspense fallback={<SkeletonCard />}>
                <RebalancingStatusCard
                  marketSignal={signal ?? undefined}
                  onPortfolioSelect={handlePortfolioSelectFromDiagnosis}
                  signalDisplay="none"
                  showAllInsights={true}
                  showHeaderBadge={false}
                />
              </Suspense>
            </ErrorBoundary>
            {signal && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={1} />}>
                  <MarketSignalBanner signal={signal} />
                </Suspense>
              </ErrorBoundary>
            )}
            {inflationSummary && inflationSummary.length > 0 && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={1} />}>
                  <InflationSummaryCard data={inflationSummary} />
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

        {/* ── 포트폴리오 탭: 목표 역산 추천 + 목록 관리 + 분석/실행 ── */}
        {localTab === "포트폴리오" && (
          <>
            <ErrorBoundary variant="section">
              <Suspense fallback={<SkeletonCard />}>
                <RecommendationCard
                  onApplied={(id) => handlePortfolioSelectFromDiagnosis(id, false, true)}
                  onCreatePortfolio={(items, name, accountIds) => {
                    setPrefillItems(items);
                    setPrefillName(name);
                    setPrefillAccountIds(accountIds ?? null);
                  }}
                />
              </Suspense>
            </ErrorBoundary>
            <Suspense fallback={<SkeletonCard />}>
              <PortfolioManageTab
                selectedPortfolioId={portfolioId}
                onAnalyze={handlePortfolioChange}
                prefillItems={prefillItems}
                prefillName={prefillName}
                prefillAccountIds={prefillAccountIds}
                onPrefillConsumed={() => {
                  setPrefillItems(null);
                  setPrefillAccountIds(null);
                }}
              />
            </Suspense>
            {portfolioId && (
              <div ref={executionRef}>
                <div className="flex items-center gap-3 px-1">
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                  <span className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide whitespace-nowrap">
                    분석 및 실행
                  </span>
                  <div className="flex-1 h-px bg-gray-200 dark:bg-gray-700" />
                </div>
                <Suspense fallback={<SkeletonCard />}>
                  <PortfolioExecutionTab portfolioId={portfolioId} />
                </Suspense>
              </div>
            )}
          </>
        )}

        {/* ── 백테스팅 탭 ── */}
        {localTab === "백테스팅" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard />}>
              <BacktestTab />
            </Suspense>
          </ErrorBoundary>
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
