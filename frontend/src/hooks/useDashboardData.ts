import { useQuery } from "@tanstack/react-query";
import { fetchAccounts } from "@/api/assets";
import { fetchDashboard } from "@/api/dashboard";
import { fetchDartDisclosures } from "@/api/dart";
import { fetchDCAAnalysis } from "@/api/invest";
import { fetchAllocationHistory, fetchPortfolioOverviewLite } from "@/api/portfolios";
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

  // lazy 컴포넌트(AllocationHistoryChart, DisclosureFeedCard)가 마운트되기 전에 미리 fetch해
  // waterfall(chunk 다운로드 완료 후 API 호출 시작)을 제거한다.
  // 반환값은 사용하지 않으며, 캐시에 채워두는 것이 목적이다.
  useQuery({
    queryKey: QUERY_KEYS.allocationHistory(12),
    queryFn: () => fetchAllocationHistory(12),
    staleTime: STALE_TIME.LONG,  // 1시간 — 백엔드 Redis TTL 1일에 맞게 보수적 설정
    gcTime: STALE_TIME.LONG,
  });
  useQuery({
    queryKey: QUERY_KEYS.dartDisclosures(30),
    queryFn: () => fetchDartDisclosures(30),
    staleTime: STALE_TIME.LONG,
    retry: false,  // DART 키 미설정 시 422 → 불필요한 재시도 방지
  });

  return { data, isLoading, error, dataUpdatedAt, overview, overviewLoading, dcaData, accounts, accountsLoading, exchangeRate };
}
