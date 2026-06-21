import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchIndicatorCalendar,
  fetchIndicatorHistory,
  fetchIndicatorSubscriptions,
  fetchIndicators,
  subscribeIndicator,
  unsubscribeIndicator,
} from "@/api/economicIndicators";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export function useEconomicIndicators() {
  return useQuery({
    queryKey: QUERY_KEYS.economicIndicators,
    queryFn: fetchIndicators,
    staleTime: STALE_TIME.LONG,
  });
}

export function useIndicatorCalendar() {
  return useQuery({
    queryKey: QUERY_KEYS.economicIndicatorCalendar,
    queryFn: fetchIndicatorCalendar,
    staleTime: STALE_TIME.LONG,
  });
}

export function useIndicatorHistory(code: string, months = 24) {
  return useQuery({
    queryKey: QUERY_KEYS.economicIndicatorHistory(code, months),
    queryFn: () => fetchIndicatorHistory(code, months),
    staleTime: STALE_TIME.LONG,
    enabled: !!code,
  });
}

export function useIndicatorSubscriptions() {
  return useQuery({
    queryKey: QUERY_KEYS.economicIndicatorSubscriptions,
    queryFn: fetchIndicatorSubscriptions,
    staleTime: STALE_TIME.MEDIUM,
  });
}

export function useSubscribeMutation() {
  const queryClient = useQueryClient();

  const subscribe = useMutation({
    mutationFn: subscribeIndicator,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.economicIndicatorSubscriptions });
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.economicIndicators });
    },
  });

  const unsubscribe = useMutation({
    mutationFn: unsubscribeIndicator,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.economicIndicatorSubscriptions });
      void queryClient.invalidateQueries({ queryKey: QUERY_KEYS.economicIndicators });
    },
  });

  return { subscribe, unsubscribe };
}
