import { queryOptions } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fetchAccounts } from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { fetchPortfolioOverviewLite, fetchPortfolios } from "@/api/portfolios";
import { fetchSettings } from "@/api/settings";
import { fetchMarketSignal } from "@/api/marketSignals";
import {
  fetchCompositeSignalStatus,
  fetchDriftSummary,
  fetchOverallGoalRecommendation,
} from "@/api/rebalancing";

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

// 계좌 목록은 계좌 CRUD·sync 시 명시적으로 무효화되므로 오래 신선하게 둔다 — 화면마다 30초~1시간이 섞여 있어
// 리밸런싱·자산 화면에 들어갈 때마다 거의 매번 재조회됐다.
export const accountsQuery = queryOptions({
  queryKey: QUERY_KEYS.accounts,
  queryFn: () => fetchAccounts(),
  staleTime: STALE_TIME.FIVE_MINUTES,
});

// 동기화·거래 입력 시 무효화된다 — 대시보드는 여기에 폴링만 덧붙인다
export const portfolioOverviewLiteQuery = queryOptions({
  queryKey: QUERY_KEYS.portfolioOverviewLite,
  queryFn: () => fetchPortfolioOverviewLite(),
  staleTime: STALE_TIME.FIVE_MINUTES,
});

export const rebalancingAlertsQuery = queryOptions({
  queryKey: QUERY_KEYS.rebalancingAlerts,
  queryFn: () => fetchRebalancingAlerts(),
  staleTime: STALE_TIME.MEDIUM,
});

export const goalRecommendationOverallQuery = queryOptions({
  queryKey: QUERY_KEYS.goalRecommendationOverall,
  queryFn: () => fetchOverallGoalRecommendation(),
  staleTime: STALE_TIME.LONG,
  // 영속 캐시(main.tsx PERSIST_QUERY_KEYS)에 남도록 — 기본 30분 gcTime이면 탭을 한동안 안 열 때
  // 저장본에서 빠져 재방문이 다시 콜드 계산(수십 초)을 기다렸다
  gcTime: STALE_TIME.DAY,
});
