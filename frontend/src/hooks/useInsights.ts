import { useQuery } from "@tanstack/react-query";
import { fetchInsights } from "@/api/insights";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { REFETCH_INTERVAL, STALE_TIME } from "@/constants/queryConfig";

export function useInsights() {
  return useQuery({
    queryKey: QUERY_KEYS.insights,
    queryFn: fetchInsights,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
  });
}
