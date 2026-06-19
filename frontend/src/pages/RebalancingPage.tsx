import { lazy, Suspense } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchMarketSignal } from "@/api/marketSignals";
import MarketSignalBanner from "@/components/rebalancing/MarketSignalBanner";
import SkeletonCard from "@/components/common/SkeletonCard";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

const PortfolioAnalysisTab = lazy(
  () => import("../components/portfolio-analysis/PortfolioAnalysisTab"),
);

export default function RebalancingPage() {
  const [searchParams] = useSearchParams();
  const portfolioId = searchParams.get("portfolioId") ?? undefined;

  const { data: signal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.LONG,
  });

  return (
    <div className="flex flex-col min-h-full">
      {signal && (
        <div className="px-4 pt-4 lg:px-6">
          <MarketSignalBanner signal={signal} />
        </div>
      )}
      <div className="flex-1 px-4 py-4 lg:px-6">
        <Suspense fallback={<SkeletonCard />}>
          <PortfolioAnalysisTab portfolioId={portfolioId} />
        </Suspense>
      </div>
    </div>
  );
}
