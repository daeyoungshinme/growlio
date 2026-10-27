import { queryOptions } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchSettings } from "@/api/settings";
import { fetchMarketSignal } from "@/api/marketSignals";
import { fetchCompositeSignalStatus, fetchDriftSummary } from "@/api/rebalancing";

/*
 * 여러 화면이 같은 키로 조회하는 쿼리의 단일 정의 — 화면마다 queryFn·staleTime을 따로 적으면 진입 화면에 따라
 * 재조회 여부가 달라진다(포트폴리오 13곳 중 6곳이 staleTime 누락으로 전역 SHORT였다, plans/78 B2).
 * queryFn은 화살표로 감싼다 — 모듈 로드 시점에 fetch 함수를 읽지 않아, 일부 export만 목킹한 테스트에서도 import가 깨지지 않는다.
 * 사용: `useQuery(portfoliosQuery)`, 조건부면 `useQuery({ ...portfoliosQuery, enabled })`, 프리페치도 그대로 넘긴다.
 */

export const portfoliosQuery = queryOptions({
  queryKey: QUERY_KEYS.portfolios,
  queryFn: () => fetchPortfolios(),
  staleTime: STALE_TIME.MEDIUM,
});

export const settingsQuery = queryOptions({
  queryKey: QUERY_KEYS.settings,
  queryFn: () => fetchSettings(),
  staleTime: STALE_TIME.LONG,
});

export const marketSignalQuery = queryOptions({
  queryKey: QUERY_KEYS.marketSignal,
  queryFn: () => fetchMarketSignal(),
  staleTime: STALE_TIME.MEDIUM,
});

export const driftSummaryQuery = queryOptions({
  queryKey: QUERY_KEYS.driftSummary,
  queryFn: () => fetchDriftSummary(),
  staleTime: STALE_TIME.MEDIUM,
});

export const compositeSignalStatusQuery = queryOptions({
  queryKey: QUERY_KEYS.compositeSignalStatus,
  queryFn: () => fetchCompositeSignalStatus(),
  staleTime: STALE_TIME.LONG,
});
