import { lazy, Suspense, useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Wallet } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import DividendSection from "@/components/dashboard/DividendSection";
import PortfolioSummaryCard from "@/components/dashboard/PortfolioSummaryCard";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import SkeletonStatBox from "@/components/common/SkeletonStatBox";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";

const AllocationHistoryChart = lazy(() => import("../components/dashboard/AllocationHistoryChart"));
const DisclosureFeedCard = lazy(() => import("../components/dashboard/DisclosureFeedCard"));

export default function DashboardPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const handleRefresh = useCallback(async () => {
    await invalidateSyncData(qc);
    await qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard });
  }, [qc]);
  useRegisterRefresh(handleRefresh);
  const { data, isLoading, error, overview, overviewLoading, dcaData, accounts, accountsLoading, exchangeRate } = useDashboardData();

  const overallDividendYield = useMemo(() => {
    const estimated = data?.estimated_annual_dividends;
    const invested = overview?.total_invested_krw;
    if (estimated && invested && invested > 0) return (estimated / invested) * 100;
    return null;
  }, [data?.estimated_annual_dividends, overview?.total_invested_krw]);

  const estimatedMonthly = useMemo(
    () => data?.estimated_annual_dividends != null ? Math.round(data.estimated_annual_dividends / 12) : null,
    [data]
  );

  if (isLoading) return (
    <div className="space-y-6">
      <div className="card">
        <div className="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-700 sm:flex sm:divide-x sm:divide-gray-100 sm:dark:divide-gray-700 sm:bg-transparent sm:gap-0">
          {[0, 1, 2, 3].map((i) => <SkeletonStatBox key={i} />)}
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SkeletonCard rows={4} height="h-5" />
        <SkeletonCard rows={4} height="h-5" />
      </div>
      <SkeletonCard rows={3} height="h-4" />
    </div>
  );
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <p className="text-sm text-red-500">데이터를 불러오지 못했습니다</p>
      <button
        onClick={() => qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard })}
        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
      >
        다시 시도
      </button>
    </div>
  );

  if (!accountsLoading && accounts.length === 0) return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 sm:p-12 text-center max-w-xs sm:max-w-md w-full">
        <Wallet size={48} className="mx-auto mb-4 text-gray-300 dark:text-gray-600" />
        <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2">
          등록된 자산이 없습니다
        </h2>
        <p className="text-sm text-gray-400 dark:text-gray-500 mb-6">
          자산관리에서 계좌를 등록하면 대시보드에서 자산 현황을 확인할 수 있습니다.
        </p>
        <button
          onClick={() => navigate("/asset-management")}
          className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          자산관리로 이동
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Row 1: Hero Card — 자산 현황 + 목표 달성 전망 */}
      <ErrorBoundary variant="section">
        <HeroSummaryCard
          data={data}
          dcaData={dcaData}
          exchangeRate={exchangeRate}
        />
      </ErrorBoundary>

      {/* Row 2: 포트폴리오 요약 + 배당 현황 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">주식 포트폴리오 요약</h2>
            <Link
              to="/portfolio"
              className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              전체 보기 <ArrowRight size={14} />
            </Link>
          </div>
          <ErrorBoundary variant="section">
            <PortfolioSummaryCard
              overview={overview}
              isLoading={overviewLoading}
              stockAllocation={overview?.stock_allocation}
            />
          </ErrorBoundary>
        </div>
        <div className="card-overflow">
          <div className="flex items-center justify-between px-5 pt-4 pb-2">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">배당 현황</h2>
            <Link
              to="/portfolio?tab=배당+현황"
              className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              자세히 보기 <ArrowRight size={14} />
            </Link>
          </div>
          <ErrorBoundary variant="section">
            <DividendSection
              annualReceived={data.annual_dividends_received ?? null}
              estimatedAnnual={data.estimated_annual_dividends ?? null}
              estimatedMonthly={estimatedMonthly}
              overallDividendYield={overallDividendYield}
            />
          </ErrorBoundary>
        </div>
      </div>

      {/* Row 3: 자산 추이 */}
      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={3} height="h-4" />}>
          <AllocationHistoryChart />
        </Suspense>
      </ErrorBoundary>

      {/* Row 5: 보유 종목 DART 공시 피드 */}
      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={2} height="h-4" />}>
          <DisclosureFeedCard />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
