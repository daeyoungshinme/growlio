import { useQuery } from "@tanstack/react-query";
import { fetchDashboard } from "@/api/dashboard";
import { useExchangeRate } from "./useExchangeRate";
import { useChallenges } from "./useChallenges";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME, REFETCH_INTERVAL } from "@/constants/queryConfig";
import { isNativePlatform } from "@/utils/platform";
import {
  accountsQuery,
  dcaAnalysisQuery,
  marketSignalQuery,
  portfolioOverviewLiteQuery,
} from "@/api/queryOptions";

// 네이티브 앱은 포그라운드에 있는 동안만 쓰이고 복귀 시 갱신되므로 주기 폴링을 끈다(PortfolioPage와 동일) —
// 화면을 켜 둔 채 두면 5분마다 대시보드·overview 재계산 요청이 이어졌다
const DASHBOARD_POLL = isNativePlatform() ? false : REFETCH_INTERVAL.DASHBOARD;

export function useDashboardData() {
  const { data, isLoading, error, dataUpdatedAt, refetch } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    staleTime: STALE_TIME.EXCHANGE_RATE, // 5분 — 백엔드 캐시 TTL(5분)과 동기화
    refetchInterval: DASHBOARD_POLL,
    refetchOnWindowFocus: false,
  });

  const { data: overview } = useQuery({
    ...portfolioOverviewLiteQuery,
    refetchInterval: DASHBOARD_POLL,
    refetchOnWindowFocus: false,
  });

  const { data: dcaData, isLoading: dcaLoading } = useQuery(dcaAnalysisQuery);

  const { data: accounts = [], isLoading: accountsLoading } = useQuery(accountsQuery);

  const { data: challenges = [] } = useChallenges();

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
    refetch,
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
