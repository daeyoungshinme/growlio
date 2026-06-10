import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchAIAnalysis, type AIAnalysisResponse } from "@/api/aiAnalysis";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export function useAIAnalysis() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: QUERY_KEYS.aiAnalysis,
    queryFn: () => fetchAIAnalysis(false),
    staleTime: STALE_TIME.LONG,
    retry: 1,
  });

  const refreshMutation = useMutation({
    mutationFn: () => fetchAIAnalysis(true),
    onSuccess: (data: AIAnalysisResponse) => {
      qc.setQueryData(QUERY_KEYS.aiAnalysis, data);
    },
  });

  return {
    ...query,
    refresh: refreshMutation.mutate,
    refreshing: refreshMutation.isPending,
  };
}
