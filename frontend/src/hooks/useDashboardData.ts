import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { fetchDashboard } from "@/api/dashboard";
import { fetchDCAAnalysis } from "@/api/invest";
import { fetchPortfolioOverviewLite } from "@/api/portfolios";
import { useExchangeRate } from "./useExchangeRate";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME, REFETCH_INTERVAL } from "@/constants/queryConfig";

export function useDashboardData() {
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    staleTime: STALE_TIME.EXCHANGE_RATE,  // 5분 — 백엔드 Redis TTL(5분)과 동기화
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
    refetchOnWindowFocus: false,
  });

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverviewLite,
    queryFn: fetchPortfolioOverviewLite,
    staleTime: STALE_TIME.EXCHANGE_RATE,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
    refetchOnWindowFocus: false,
  });

  const { data: dcaData } = useQuery({
    queryKey: QUERY_KEYS.dcaAnalysis,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.EXCHANGE_RATE,
  });

  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.EXCHANGE_RATE,  // 5분 — 계좌 목록은 자주 변하지 않음
  });

  const exchangeRate = useExchangeRate();

  return { data, isLoading, error, dataUpdatedAt, overview, overviewLoading, dcaData, accounts, accountsLoading, exchangeRate };
}
