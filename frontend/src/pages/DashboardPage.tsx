import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Wallet } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import InvestmentGoalCard from "@/components/dashboard/InvestmentGoalCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";

const RebalancingStatusCard = lazy(
  () => import("../components/dashboard/RebalancingStatusCard"),
);

const AllocationHistoryChart = lazy(() => import("../components/dashboard/AllocationHistoryChart"));

export default function DashboardPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [syncing, setSyncing] = useState(false);

  const handleRefresh = useCallback(async () => {
    await invalidateSyncData(qc);
  }, [qc]);
  useRegisterRefresh(handleRefresh);

  const handleSync = useCallback(async () => {
    setSyncing(true);
    try {
      await invalidateSyncData(qc);
    } finally {
      setSyncing(false);
    }
  }, [qc]);

  const {
    data,
    isLoading,
    error,
    dataUpdatedAt,
    overview,
    dcaData,
    accounts,
    accountsLoading,
    exchangeRate,
    marketSignal,
  } = useDashboardData();

  const overallDividendYield = useMemo(() => {
    const estimated = data?.estimated_annual_dividends;
    const invested = overview?.total_invested_krw;
    if (estimated && invested && invested > 0) return (estimated / invested) * 100;
    return null;
  }, [data?.estimated_annual_dividends, overview?.total_invested_krw]);

  if (!isLoading && (error || !data))
    return (
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

  if (!accountsLoading && accounts.length === 0)
    return (
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
            onClick={() => navigate("/settings")}
            className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            자산관리로 이동
          </button>
        </div>
      </div>
    );

  return (
    <>
      {/* 데스크탑 동기화 버튼 — space-y-6 밖으로 분리하여 HeroSummaryCard에 margin-top이 생기지 않도록 */}
      <div className="hidden lg:flex items-center justify-end mb-4">
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          {syncing ? "갱신 중..." : "데이터 갱신"}
        </button>
      </div>
      <div className="space-y-6">
      {/* Row 1: Hero Card — 자산 현황 */}
      <ErrorBoundary variant="section">
        <HeroSummaryCard
          data={data}
          exchangeRate={exchangeRate}
          dataUpdatedAt={dataUpdatedAt}
          isLoading={isLoading}
          onSync={handleSync}
          syncing={syncing}
          estimatedAnnualDividends={data?.estimated_annual_dividends ?? null}
          dividendYield={overallDividendYield}
        />
      </ErrorBoundary>

      {/* Row 2: 투자 목표 달성 현황 */}
      <ErrorBoundary variant="section">
        <InvestmentGoalCard data={data} dcaData={dcaData} isLoading={isLoading} />
      </ErrorBoundary>

      {/* Row 3: 리밸런싱 진단 요약 */}
      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={2} />}>
          <RebalancingStatusCard
            showAllInsights={false}
            showDriftRows={true}
            maxDriftRows={3}
            hideSignalBanner={true}
            marketSignal={marketSignal}
            onPortfolioSelect={(id) =>
              navigate(`/rebalancing?rtab=포트폴리오&portfolioId=${id}`)
            }
          />
        </Suspense>
      </ErrorBoundary>

      {/* Row 4: 자산 추이 */}
      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={3} height="h-4" />}>
          <AllocationHistoryChart />
        </Suspense>
      </ErrorBoundary>
    </div>
    </>
  );
}
