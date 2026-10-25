import { useQuery } from "@tanstack/react-query";
import {
  fetchDividendByTicker,
  fetchDividendPositions,
  fetchDividendSummary,
} from "@/api/dividends";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

/**
 * @param enabled 종목별 배당수익률(dividend-positions) 조회 여부 — 보유 종목 표의 배당 열에 쓴다
 * @param detailsEnabled 배당 요약·종목별 배당 상세 조회 여부 — 배당 탭에서만 필요하다. by-ticker는 외부 배당
 *   provider 체인을 타 느린데, 예전엔 기본 탭(종목 현황)에서도 함께 불러 배당 열 로딩까지 그만큼 늦췄다.
 */
export function useDividendData(
  enabled: boolean,
  accountId?: string | null,
  detailsEnabled: boolean = enabled,
) {
  const {
    data: dividendPositions = [],
    isLoading: positionsLoading,
    isError: positionsError,
  } = useQuery({
    queryKey: QUERY_KEYS.dividendPositions(accountId),
    queryFn: () => fetchDividendPositions(accountId),
    staleTime: STALE_TIME.LONG,
    enabled,
  });

  const {
    data: dividendSummary,
    isLoading: summaryLoading,
    isError: summaryError,
  } = useQuery({
    queryKey: QUERY_KEYS.dividendSummary(accountId),
    queryFn: () => fetchDividendSummary(accountId),
    staleTime: STALE_TIME.LONG,
    enabled: enabled && detailsEnabled,
  });

  const {
    data: dividendByTicker = [],
    isLoading: byTickerLoading,
    isError: byTickerError,
  } = useQuery({
    queryKey: QUERY_KEYS.dividendByTicker(accountId),
    queryFn: () => fetchDividendByTicker(accountId),
    staleTime: STALE_TIME.LONG,
    enabled: enabled && detailsEnabled,
  });

  return {
    dividendPositions,
    dividendSummary,
    dividendByTicker,
    // 켜진 쿼리 중 하나라도 첫 로딩 중이면 로딩으로 취급(꺼진 쿼리는 isLoading=false) — /dividends/by-ticker(외부 배당 provider 호출로
    // 상대적으로 느림)가 dividendPositions보다 늦게 끝나면, isLoading을 첫 쿼리만으로 판단할 경우
    // by-ticker가 아직 빈 배열인 상태로 "배당 데이터 없음" 빈 상태가 먼저 그려졌다가 뒤늦게
    // 실제 데이터로 바뀌는 깜빡임이 발생했었다.
    isLoading: positionsLoading || summaryLoading || byTickerLoading,
    isError: positionsError || summaryError || byTickerError,
  };
}
