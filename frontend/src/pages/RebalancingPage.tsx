import { lazy, Suspense, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchMarketSignal } from "@/api/marketSignals";
import MarketSignalBanner from "@/components/rebalancing/MarketSignalBanner";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const PortfolioAnalysisTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioAnalysisTab"),
);
const RebalancingAlertListTab = lazy(
  () => import("../components/portfolio-analysis/RebalancingAlertListTab"),
);

const REBALANCING_PAGE_TABS = ["포트폴리오 비중", "알림 설정"] as const;
type RebalancingPageTab = (typeof REBALANCING_PAGE_TABS)[number];

export default function RebalancingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const portfolioId = searchParams.get("portfolioId") ?? undefined;
  const rawTab = searchParams.get("rtab");
  const [localTab, setLocalTab] = useState<RebalancingPageTab>(
    REBALANCING_PAGE_TABS.includes(rawTab as RebalancingPageTab)
      ? (rawTab as RebalancingPageTab)
      : "포트폴리오 비중",
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

  const { data: signal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.LONG,
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

      {/* 시장 신호는 포트폴리오 비중 탭에서만 표시 */}
      {signal && localTab === "포트폴리오 비중" && (
        <MarketSignalBanner signal={signal} />
      )}

      <div className="flex-1">
        {localTab === "포트폴리오 비중" && (
          <Suspense fallback={<SkeletonCard />}>
            <PortfolioAnalysisTab portfolioId={portfolioId} />
          </Suspense>
        )}
        {localTab === "알림 설정" && (
          <Suspense fallback={<SkeletonCard />}>
            <RebalancingAlertListTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
