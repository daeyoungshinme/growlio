import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import type { DividendByTicker, DividendYield } from "@/types";

export interface DividendSummary {
  annual_received: number;
  estimated_annual: number;
  monthly_breakdown: { month: string; amount: number }[];
  monthly_ticker_breakdown: { month: string; ticker: string | null; amount: number }[];
}

export function useDividendData(enabled: boolean, accountId?: string | null) {
  const {
    data: dividendPositions = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: QUERY_KEYS.dividendPositions(accountId),
    queryFn: () =>
      api
        .get<
          DividendYield[]
        >("/dividends/positions", { params: { account_id: accountId || undefined } })
        .then((r) => r.data),
    staleTime: STALE_TIME.LONG,
    enabled,
  });

  const { data: dividendSummary } = useQuery({
    queryKey: QUERY_KEYS.dividendSummary(accountId),
    queryFn: () =>
      api
        .get<DividendSummary>("/dividends/summary", {
          params: { account_id: accountId || undefined },
        })
        .then((r) => r.data),
    staleTime: STALE_TIME.LONG,
    enabled,
  });

  const { data: dividendByTicker = [] } = useQuery({
    queryKey: QUERY_KEYS.dividendByTicker(accountId),
    queryFn: () =>
      api
        .get<
          DividendByTicker[]
        >("/dividends/by-ticker", { params: { account_id: accountId || undefined } })
        .then((r) => r.data),
    staleTime: STALE_TIME.LONG,
    enabled,
  });

  return { dividendPositions, dividendSummary, dividendByTicker, isLoading, isError };
}
