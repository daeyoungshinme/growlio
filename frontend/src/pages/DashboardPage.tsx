import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, RefreshCw, Wallet } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import DividendSection from "@/components/dashboard/DividendSection";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import DriftAlertSummary from "@/components/dashboard/DriftAlertSummary";
import InvestmentGoalCard from "@/components/dashboard/InvestmentGoalCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";

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
  } = useDashboardData();

  const overallDividendYield = useMemo(() => {
    const estimated = data?.estimated_annual_dividends;
    const invested = overview?.total_invested_krw;
    if (estimated && invested && invested > 0) return (estimated / invested) * 100;
    return null;
  }, [data?.estimated_annual_dividends, overview?.total_invested_krw]);

  const estimatedMonthly = useMemo(
    () =>
      data?.estimated_annual_dividends != null
        ? Math.round(data.estimated_annual_dividends / 12)
        : null,
    [data],
  );

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
    <div className="space-y-6">
      {/* Row 0: 동기화 버튼 (데스크탑) */}
      <div className="hidden lg:flex items-center justify-end">
        <button
          onClick={handleSync}
          disabled={syncing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          {syncing ? "갱신 중..." : "데이터 갱신"}
        </button>
      </div>

      {/* Row 1: Hero Card — 자산 현황 */}
      <ErrorBoundary variant="section">
        <HeroSummaryCard
          data={data}
          exchangeRate={exchangeRate}
          dataUpdatedAt={dataUpdatedAt}
          isLoading={isLoading}
          onSync={handleSync}
          syncing={syncing}
        />
      </ErrorBoundary>

      {/* Row 2: 투자 목표 달성 현황 */}
      <ErrorBoundary variant="section">
        <InvestmentGoalCard data={data} dcaData={dcaData} isLoading={isLoading} />
      </ErrorBoundary>

      {/* Row 3: 리밸런싱 현황 요약 */}
      <ErrorBoundary variant="section">
        <DriftAlertSummary />
      </ErrorBoundary>

      {/* Row 4: 배당 현황 */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">배당 현황</h2>
          <Link
            to="/assets?tab=투자현황&portfolioTab=배당"
            className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            자세히 보기 <ArrowRight size={14} />
          </Link>
        </div>
        <ErrorBoundary variant="section">
          <DividendSection
            annualReceived={data?.annual_dividends_received ?? null}
            estimatedAnnual={data?.estimated_annual_dividends ?? null}
            estimatedMonthly={estimatedMonthly}
            overallDividendYield={overallDividendYield}
            isLoading={isLoading}
          />
        </ErrorBoundary>
      </div>

      {/* Row 5: 자산 추이 */}
      <ErrorBoundary variant="section">
        <Suspense fallback={<SkeletonCard rows={3} height="h-4" />}>
          <AllocationHistoryChart />
        </Suspense>
      </ErrorBoundary>
    </div>
  );
}
