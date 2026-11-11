import { lazy, Suspense, useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Circle, RefreshCw, Wallet } from "lucide-react";
import { Link } from "react-router-dom";
import { useDashboardData } from "@/hooks/useDashboardData";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import HeroSummaryCard from "@/components/dashboard/HeroSummaryCard";
import InvestmentGoalCard from "@/components/dashboard/InvestmentGoalCard";
import ChallengeProgressCard from "@/components/dashboard/ChallengeProgressCard";
import ChallengeEmptyStateCard from "@/components/dashboard/ChallengeEmptyStateCard";
import SetupTargetPortfolioBanner from "@/components/dashboard/SetupTargetPortfolioBanner";
import SkeletonCard from "@/components/common/SkeletonCard";
import ErrorBoundary from "@/components/ErrorBoundary";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { portfoliosQuery } from "@/api/queryOptions";
import { assetManagementUrl } from "@/utils/tabUrl";
import PageLoadError from "@/components/common/PageLoadError";

const ActionItemsCard = lazy(() => import("../components/dashboard/ActionItemsCard"));

const AllocationHistoryCard = lazy(() => import("../components/dashboard/AllocationHistoryCard"));

const ONBOARDING_STEPS = [
  {
    title: "1단계: 계좌 등록",
    description: "은행·증권 계좌를 연결하세요.",
    to: assetManagementUrl("증권계좌"),
    cta: "등록하기 →",
  },
  {
    title: "2단계: 포트폴리오 구성",
    description: "목표 비중을 설정해 리밸런싱을 관리하세요.",
    to: rebalancingUrl({ tab: "포트폴리오" }),
    cta: "둘러보기 →",
  },
  {
    title: "3단계: 투자 목표 설정",
    description: "자산·배당·입금 목표를 입력하세요.",
    to: "/invest-plan",
    cta: "설정하기 →",
  },
];

function OnboardingChecklist() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 sm:p-12 max-w-md w-full">
        <Wallet size={40} className="mx-auto mb-4 text-blue-400" />
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mb-1 text-center">
          Growlio 시작하기
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 text-center">
          아래 단계를 완료하면 대시보드가 활성화됩니다.
        </p>

        <ol className="space-y-4">
          {/* 계좌가 없을 때만 표시되는 화면이라 전부 미완료 */}
          {ONBOARDING_STEPS.map((step) => (
            <li key={step.title} className="flex items-start gap-3">
              <Circle size={20} className="mt-0.5 shrink-0 text-gray-300 dark:text-gray-600" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{step.title}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{step.description}</p>
              </div>
              <Link
                to={step.to}
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} -my-2 shrink-0 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline`}
              >
                {step.cta}
              </Link>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const qc = useQueryClient();
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
    dataUpdatedAt,
    refetch,
    overview,
    dcaData,
    dcaLoading,
    accounts,
    accountsLoading,
    accountsFailed,
    exchangeRate,
    marketSignal,
    challenges,
    challengesLoading,
  } = useDashboardData();

  // SetupTargetPortfolioBanner와 동일 queryKey를 재사용 — 캐시 공유로 추가 네트워크 요청 없음.
  const { data: portfolios } = useQuery(portfoliosQuery);
  const isBrandNewUser =
    !data?.goal_amount &&
    !data?.annual_deposit_goal &&
    !data?.annual_dividend_goal &&
    portfolios?.length === 0;

  if (!isLoading && !data)
    return <PageLoadError message="데이터를 불러오지 못했습니다" onRetry={() => void refetch()} />;

  // 조회 실패는 "계좌 없음"이 아니다 — 기존 사용자에게 시작 안내가 뜨지 않게 한다
  if (!accountsLoading && !accountsFailed && accounts.length === 0) return <OnboardingChecklist />;

  return (
    <>
      <h1 className="sr-only">홈</h1>
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
      {/* 모바일 카드 간격 24→12px — 카드 7~8장 기준 약 100px 절약 (docs/plans/67 Phase 3) */}
      <div className="space-y-3 sm:space-y-6">
        <ErrorBoundary variant="section">
          <SetupTargetPortfolioBanner />
        </ErrorBoundary>

        {/* Hero: 자산 현황 */}
        <ErrorBoundary variant="section">
          <HeroSummaryCard
            overview={overview}
            data={data}
            exchangeRate={exchangeRate}
            dataUpdatedAt={dataUpdatedAt}
            isLoading={isLoading}
            onSync={handleSync}
            syncing={syncing}
          />
        </ErrorBoundary>

        {/* 지금 할 일: 리밸런싱·자동매수 예수금·세금·챌린지 행동 신호를 우선순위 1장으로 (docs/plans/50 M5)
            + 하단 리밸런싱 상태·시장 신호 한 줄 — 예전 별도 "리밸런싱 점검" 카드를 흡수 (docs/plans/73) */}
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard rows={2} />}>
            <ActionItemsCard marketSignal={marketSignal} />
          </Suspense>
        </ErrorBoundary>

        {/* 투자 목표 달성 현황 */}
        <ErrorBoundary variant="section">
          <InvestmentGoalCard data={data} dcaData={dcaData} isLoading={isLoading || dcaLoading} />
        </ErrorBoundary>

        {/* 적립 챌린지 진행 현황 — ACTIVE 챌린지가 있으면 진행률, 없으면 만들기 유도(닫기 가능) */}
        <ErrorBoundary variant="section">
          {/* 목록이 오기 전엔 빈 상태 카드 대신 자리만 — 진행 중 챌린지가 있는 사용자에게 "만들기" 카드가 먼저
              떴다가 바뀌던 깜빡임 방지(plans/125 C6) */}
          {challengesLoading ? (
            <SkeletonCard rows={2} />
          ) : challenges.some((c) => c.status === "ACTIVE") ? (
            <ChallengeProgressCard challenges={challenges} />
          ) : (
            <ChallengeEmptyStateCard />
          )}
        </ErrorBoundary>

        {/* 자산 추이 — 과거지향 정보라 최하단 유지. 목표·포트폴리오 모두 없는 완전 신규 유저는 추이 데이터가
            없어 의미가 없으므로 생략(목표/포트폴리오를 하나라도 설정하면 다음 방문부터 노출됨) */}
        {!isBrandNewUser && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard rows={3} height="h-4" />}>
              <AllocationHistoryCard />
            </Suspense>
          </ErrorBoundary>
        )}
      </div>
    </>
  );
}
