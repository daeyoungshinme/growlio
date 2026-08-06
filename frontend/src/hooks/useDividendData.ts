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
    isLoading: positionsLoading,
    isError: positionsError,
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

  const {
    data: dividendSummary,
    isLoading: summaryLoading,
    isError: summaryError,
  } = useQuery({
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

  const {
    data: dividendByTicker = [],
    isLoading: byTickerLoading,
    isError: byTickerError,
  } = useQuery({
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

  return {
    dividendPositions,
    dividendSummary,
    dividendByTicker,
    // 세 쿼리 중 하나라도 첫 로딩 중이면 로딩으로 취급 — /dividends/by-ticker(외부 배당 provider 호출로
    // 상대적으로 느림)가 dividendPositions보다 늦게 끝나면, isLoading을 첫 쿼리만으로 판단할 경우
    // by-ticker가 아직 빈 배열인 상태로 "배당 데이터 없음" 빈 상태가 먼저 그려졌다가 뒤늦게
    // 실제 데이터로 바뀌는 깜빡임이 발생했었다.
    isLoading: positionsLoading || summaryLoading || byTickerLoading,
    isError: positionsError || summaryError || byTickerError,
  };
}
