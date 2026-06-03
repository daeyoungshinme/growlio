import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "../api/assets";
import { fetchDashboard } from "../api/dashboard";
import { fetchDCAAnalysis } from "../api/invest";
import { fetchPortfolioOverview } from "../api/portfolios";
import { useExchangeRate } from "./useExchangeRate";
import { QUERY_KEYS } from "../constants/queryKeys";
import { STALE_TIME, REFETCH_INTERVAL } from "../constants/queryConfig";

export function useDashboardData() {
  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
    refetchOnWindowFocus: false,
  });

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverview,
    queryFn: fetchPortfolioOverview,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
    refetchOnWindowFocus: false,
  });

  const { data: dcaData } = useQuery({
    queryKey: QUERY_KEYS.investDca,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
  });

  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });

  const exchangeRate = useExchangeRate();

  return { data, isLoading, error, overview, overviewLoading, dcaData, accounts, accountsLoading, exchangeRate };
}
