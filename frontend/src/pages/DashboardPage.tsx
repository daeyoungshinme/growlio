import { lazy, Suspense, useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Circle, RefreshCw, Wallet } from "lucide-react";
import { useNavigate, Link } from "react-router-dom";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import InvestmentGoalCard from "@/components/dashboard/InvestmentGoalCard";
import SetupTargetPortfolioBanner from "@/components/dashboard/SetupTargetPortfolioBanner";
import SkeletonCard from "@/components/common/SkeletonCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { QUERY_KEYS } from "@/constants/queryKeys";

const RebalancingStatusCard = lazy(() => import("../components/dashboard/RebalancingStatusCard"));

const InvestmentSnapshotCard = lazy(() => import("../components/dashboard/InvestmentSnapshotCard"));

const AllocationHistoryChart = lazy(() => import("../components/dashboard/AllocationHistoryChart"));

function OnboardingChecklist() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-8 sm:p-12 max-w-xs sm:max-w-md w-full">
        <Wallet size={40} className="mx-auto mb-4 text-blue-400" />
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-1 text-center">
          Growlio 시작하기
        </h2>
        <p className="text-sm text-gray-400 dark:text-gray-500 mb-6 text-center">
          아래 단계를 완료하면 대시보드가 활성화됩니다.
        </p>

        <ol className="space-y-4">
          {/* Step 1: 계좌 등록 — 이 화면은 계좌가 없을 때만 표시되므로 미완료 */}
          <li className="flex items-start gap-3">
            <Circle size={20} className="mt-0.5 shrink-0 text-gray-300 dark:text-gray-600" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                1단계: 계좌 등록
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500">
                은행·증권 계좌를 연결하세요.
              </p>
            </div>
            <Link
              to="/assets?tab=계좌관리"
              className="shrink-0 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
            >
              등록하기 →
            </Link>
          </li>

          <li className="flex items-start gap-3">
            <Circle size={20} className="mt-0.5 shrink-0 text-gray-300 dark:text-gray-600" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-500">
                2단계: 포트폴리오 구성
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-600">
                목표 비중을 설정해 리밸런싱을 관리하세요.
              </p>
            </div>
            <span className="shrink-0 text-xs text-gray-300 dark:text-gray-600">계좌 등록 후</span>
          </li>

          <li className="flex items-start gap-3">
            <Circle size={20} className="mt-0.5 shrink-0 text-gray-300 dark:text-gray-600" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-500">
                3단계: 투자 목표 설정
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-600">
                자산·배당·입금 목표를 입력하세요.
              </p>
            </div>
            <Link
              to="/invest-plan"
              className="shrink-0 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline"
            >
              설정하기 →
            </Link>
          </li>
        </ol>
      </div>
    </div>
  );
}

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

  if (!accountsLoading && accounts.length === 0) return <OnboardingChecklist />;

  return (
    <>
      {/* 데스크탑 동기화 버튼 */}
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
        <ErrorBoundary variant="section">
          <SetupTargetPortfolioBanner />
        </ErrorBoundary>

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

        {/* Row 3: 주식 투자 현황 */}
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard />}>
            <InvestmentSnapshotCard overview={overview} data={data} />
          </Suspense>
        </ErrorBoundary>

        {/* Row 4: 리밸런싱 진단 요약 */}
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard rows={2} />}>
            <RebalancingStatusCard
              showAllInsights={false}
              showDriftRows={true}
              maxDriftRows={3}
              hideSignalBanner={true}
              marketSignal={marketSignal}
              onPortfolioSelect={(id) => navigate(`/rebalancing?rtab=포트폴리오&portfolioId=${id}`)}
            />
          </Suspense>
        </ErrorBoundary>

        {/* Row 5: 자산 추이 */}
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard rows={3} height="h-4" />}>
            <AllocationHistoryChart />
          </Suspense>
        </ErrorBoundary>
      </div>
    </>
  );
}
