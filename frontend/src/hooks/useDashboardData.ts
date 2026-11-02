import { useQuery } from "@tanstack/react-query";
import { useExchangeRate } from "./useExchangeRate";
import { useChallenges } from "./useChallenges";
import { REFETCH_INTERVAL } from "@/constants/queryConfig";
import { isNativePlatform } from "@/utils/platform";
import {
  accountsQuery,
  dashboardQuery,
  dcaAnalysisQuery,
  marketSignalQuery,
  portfolioOverviewLiteQuery,
} from "@/api/queryOptions";

// 네이티브 앱은 포그라운드에 있는 동안만 쓰이고 복귀 시 갱신되므로 주기 폴링을 끈다(PortfolioPage와 동일) —
// 화면을 켜 둔 채 두면 5분마다 대시보드·overview 재계산 요청이 이어졌다
const DASHBOARD_POLL = isNativePlatform() ? false : REFETCH_INTERVAL.DASHBOARD;

export function useDashboardData() {
  const { data, isLoading, error, dataUpdatedAt, refetch } = useQuery({
    ...dashboardQuery,
    refetchInterval: DASHBOARD_POLL,
    refetchOnWindowFocus: false,
  });

  const { data: overview } = useQuery({
    ...portfolioOverviewLiteQuery,
    refetchInterval: DASHBOARD_POLL,
    refetchOnWindowFocus: false,
  });

  const { data: dcaData, isLoading: dcaLoading } = useQuery(dcaAnalysisQuery);

  const {
    data: accounts = [],
    isLoading: accountsLoading,
    isError: accountsFailed,
  } = useQuery(accountsQuery);

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
    accountsFailed,
    exchangeRate,
    marketSignal,
    challenges,
  };
}
