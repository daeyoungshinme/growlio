import { lazy, Suspense, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { fetchMarketSignal } from "@/api/marketSignals";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import Modal from "@/components/common/Modal";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const RebalancingStatusCard = lazy(
  () => import("../components/dashboard/RebalancingStatusCard"),
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
const RebalancingAlertListTab = lazy(
  () => import("../components/rebalancing/RebalancingAlertListTab"),
);
const MarketSignalBanner = lazy(
  () => import("../components/rebalancing/MarketSignalBanner"),
);

const REBALANCING_PAGE_TABS = ["포트폴리오 관리", "이력"] as const;
type RebalancingPageTab = (typeof REBALANCING_PAGE_TABS)[number];

export default function RebalancingPage() {
  const [alertOpen, setAlertOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const portfolioId = searchParams.get("portfolioId") ?? undefined;
  const rawTab = searchParams.get("rtab");
  const [localTab, setLocalTab] = useState<RebalancingPageTab>(
    REBALANCING_PAGE_TABS.includes(rawTab as RebalancingPageTab)
      ? (rawTab as RebalancingPageTab)
      : "포트폴리오 관리",
  );

  const handleTabChange = (tab: RebalancingPageTab) => {
    setLocalTab(tab);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("rtab", tab);
        return next;
      },
      { replace: true },
    );
  };

  const handlePortfolioChange = (id: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set("portfolioId", id);
        return next;
      },
      { replace: true },
    );
  };

  const handleAnalyze = (id: string) => {
    handlePortfolioChange(id);
  };

  const { data: signal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.LONG,
  });

  return (
    <div className="flex flex-col min-h-full gap-4">
      <div className="flex items-center justify-between px-1">
        <Tabs
          tabs={REBALANCING_PAGE_TABS}
          activeTab={localTab}
          onChange={handleTabChange}
          variant="pill"
        />
        <button
          onClick={() => setAlertOpen(true)}
          aria-label="리밸런싱 알림 설정"
          className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:text-blue-400 dark:hover:bg-blue-950/30 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
        >
          <Bell size={18} />
        </button>
      </div>

      <div className="flex-1 flex flex-col gap-4">
        {localTab === "포트폴리오 관리" && (
          <>
            <ErrorBoundary variant="section">
              <Suspense fallback={<SkeletonCard />}>
                <RebalancingStatusCard
                  marketSignal={signal ?? undefined}
                  onPortfolioSelect={handlePortfolioChange}
                  hideSignalBanner={true}
                  showAllInsights={true}
                />
              </Suspense>
            </ErrorBoundary>
            {signal && (
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={3} />}>
                  <MarketSignalBanner
                    signal={signal}
                    defaultExpanded={signal.composite_level !== "GREEN"}
                  />
                </Suspense>
              </ErrorBoundary>
            )}
            <Suspense fallback={<SkeletonCard />}>
              <PortfolioManageTab
                selectedPortfolioId={portfolioId}
                onAnalyze={handleAnalyze}
              />
            </Suspense>
            {portfolioId && (
              <Suspense fallback={<SkeletonCard />}>
                <PortfolioExecutionTab portfolioId={portfolioId} />
              </Suspense>
            )}
          </>
        )}
        {localTab === "이력" && (
          <Suspense fallback={<SkeletonCard />}>
            <RebalancingHistoryTab />
          </Suspense>
        )}
      </div>

      {alertOpen && (
        <Modal title="리밸런싱 자동화 설정" onClose={() => setAlertOpen(false)} closeOnBackdrop>
          <div className="p-4 overflow-y-auto">
            <Suspense fallback={<SkeletonCard rows={4} />}>
              <RebalancingAlertListTab />
            </Suspense>
          </div>
        </Modal>
      )}
    </div>
  );
}
