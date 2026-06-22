import { lazy, Suspense, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { fetchMarketSignal } from "@/api/marketSignals";
import MarketSignalBanner from "@/components/rebalancing/MarketSignalBanner";
import SkeletonCard from "@/components/common/SkeletonCard";
import Tabs from "@/components/common/Tabs";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const PortfolioAnalysisTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioAnalysisTab"),
);
const RebalancingHistoryTab = lazy(
  () => import("../components/rebalancing/RebalancingHistoryTab"),
);

const REBALANCING_PAGE_TABS = ["포트폴리오 비중", "실행 이력"] as const;
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
      <div className="flex items-center justify-between px-1">
        <Tabs
          tabs={REBALANCING_PAGE_TABS}
          activeTab={localTab}
          onChange={handleTabChange}
          variant="pill"
        />
        <Link
          to="/settings#rebalancing-alerts"
          aria-label="알림 설정으로 이동"
          className="p-2 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:text-blue-400 dark:hover:bg-blue-950/30 rounded-lg transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
        >
          <Bell size={18} />
        </Link>
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
        {localTab === "실행 이력" && (
          <Suspense fallback={<SkeletonCard />}>
            <RebalancingHistoryTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
