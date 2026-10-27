import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { fetchDashboard } from "@/api/dashboard";
import { fetchDCAAnalysis } from "@/api/invest";
import { fetchPortfolioOverviewLite } from "@/api/portfolios";
import { fetchChallenges } from "@/api/challenges";
import { useExchangeRate } from "./useExchangeRate";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME, REFETCH_INTERVAL } from "@/constants/queryConfig";
import { isNativePlatform } from "@/utils/platform";
import { marketSignalQuery } from "@/api/queryOptions";

// 네이티브 앱은 포그라운드에 있는 동안만 쓰이고 복귀 시 갱신되므로 주기 폴링을 끈다(PortfolioPage와 동일) —
// 화면을 켜 둔 채 두면 5분마다 대시보드·overview 재계산 요청이 이어졌다
const DASHBOARD_POLL = isNativePlatform() ? false : REFETCH_INTERVAL.DASHBOARD;

export function useDashboardData() {
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    staleTime: STALE_TIME.EXCHANGE_RATE, // 5분 — 백엔드 캐시 TTL(5분)과 동기화
    refetchInterval: DASHBOARD_POLL,
    refetchOnWindowFocus: false,
  });

  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverviewLite,
    queryFn: fetchPortfolioOverviewLite,
    staleTime: STALE_TIME.EXCHANGE_RATE,
    refetchInterval: DASHBOARD_POLL,
    refetchOnWindowFocus: false,
  });

  const { data: dcaData, isLoading: dcaLoading } = useQuery({
    queryKey: QUERY_KEYS.dcaAnalysis,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.EXCHANGE_RATE, // 5분 — 계좌 목록은 자주 변하지 않음
  });

  const { data: challenges = [] } = useQuery({
    queryKey: QUERY_KEYS.challenges,
    queryFn: fetchChallenges,
    staleTime: STALE_TIME.MEDIUM,
  });

  const exchangeRate = useExchangeRate();

  const { data: marketSignal } = useQuery({
    ...marketSignalQuery,
    refetchOnWindowFocus: false,
  });

  return {
    data,
    isLoading,
    error,
    dataUpdatedAt,
    overview,
    dcaData,
    dcaLoading,
    accounts,
    accountsLoading,
    exchangeRate,
    marketSignal,
    challenges,
  };
}
