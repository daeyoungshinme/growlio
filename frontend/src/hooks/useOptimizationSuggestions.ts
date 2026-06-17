import { useQuery } from "@tanstack/react-query";
import { fetchMonthlyOptimization } from "@/api/dividends";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export function useOptimizationSuggestions() {
  const { data: suggestions, isLoading } = useQuery({
    queryKey: QUERY_KEYS.monthlyOptimization,
    queryFn: fetchMonthlyOptimization,
    staleTime: STALE_TIME.LONG,
  });

  return { suggestions, isLoading };
}
