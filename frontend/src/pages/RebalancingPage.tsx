import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchMarketSignal } from "@/api/marketSignals";
import { fetchPortfolioRisk } from "@/api/risk";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const RebalancingStatusCard = lazy(
  () => import("../components/dashboard/RebalancingStatusCard"),
);
const RiskMetricsCard = lazy(
  () => import("../components/rebalancing/RiskMetricsCard"),
);
const MarketSignalBanner = lazy(
  () => import("../components/rebalancing/MarketSignalBanner"),
);
const PortfolioManageTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioManageTab"),
);
const PortfolioExecutionTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioExecutionTab"),
);
const RebalancingHistoryTab = lazy(
  () => import("../components/rebalancing/RebalancingHistoryTab"),
);
const BacktestTab = lazy(
  () => import("../components/rebalancing/BacktestTab"),
);

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
    (id: string, openAlert?: boolean) => {
      setLocalTab("포트폴리오");
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("portfolioId", id);
          next.set("rtab", "포트폴리오");
          if (openAlert) {
            next.set("openAlert", "1");
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

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

      <div className="flex-1 flex flex-col gap-4">
        {/* ── 진단 탭: 시장신호 + 전체 포트폴리오 드리프트 현황 ── */}
        {localTab === "진단" && (
          <>
            {signal && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={1} />}>
                  <MarketSignalBanner signal={signal} />
                </Suspense>
              </ErrorBoundary>
            )}
            <ErrorBoundary variant="section">
              <Suspense fallback={<SkeletonCard />}>
                <RebalancingStatusCard
                  marketSignal={signal ?? undefined}
                  onPortfolioSelect={handlePortfolioSelectFromDiagnosis}
                  hideSignalBanner={true}
                  showAllInsights={true}
                />
              </Suspense>
            </ErrorBoundary>
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
                selectedPortfolioId={portfolioId}
                onAnalyze={handlePortfolioChange}
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
