import { defaultShouldDehydrateQuery, type Query } from "@tanstack/react-query";

export const PERSIST_CACHE_KEY = "rq-persist-cache";

/**
 * persist 캐시 버전 — main.tsx `PERSIST_QUERY_KEYS`에 든 쿼리의 응답 형태를 호환되지 않게 바꾸면(필드 삭제·이름/타입 변경,
 * 새 필드를 non-optional로 읽기 시작) 날짜로 올린다. 올리면 모든 기기의 24h 캐시가 한 번 버려진다.
 * 배포마다 자동으로 바꾸지 않는 건 매 배포 첫 부팅이 콜드가 되어 persist의 목적(즉시 표시)이 사라지기 때문이다.
 * "v1"(2026-06-09)에서 한 번도 안 올라가 그 사이 dashboard·portfolios 응답 변경이 누적돼 있었다(plans/61 B4).
 */
export const PERSIST_CACHE_BUSTER = "2026-10-20";

/** 앱 재시작 시 즉시 표시할 쿼리(첫 키 기준) — 응답 형태를 바꾸면 PERSIST_CACHE_BUSTER를 올린다. */
const PERSIST_QUERY_KEYS = new Set([
  "dashboard",
  "portfolio-overview",
  "accounts",
  "dca-analysis",
  "goal-recommendation",
]);

/**
 * persist 대상 판정. 커스텀 필터는 라이브러리 기본값(성공한 쿼리만)을 대체하므로 반드시 합친다 —
 * 빠뜨리면 실패·진행 중 쿼리까지 저장돼 다음 부팅이 에러 화면으로 시작한다(plans/61 B4).
 */
export function shouldPersistQuery(query: Query): boolean {
  return defaultShouldDehydrateQuery(query) && PERSIST_QUERY_KEYS.has(query.queryKey[0] as string);
}

export const STALE_TIME = {
  /** 항상 새로 조회 — 열 때마다 최신이어야 하는 화면(승인 확인·추천 미리보기) */
  NONE: 0,
  VERY_SHORT: 15_000,
  SHORT: 30_000,
  MEDIUM: 60_000,
  LONG: 1000 * 60 * 60,
  EXCHANGE_RATE: 5 * 60 * 1000,
  FIVE_MINUTES: 5 * 60 * 1000,
} as const;

export const REFETCH_INTERVAL = {
  DASHBOARD: 300_000,
  PORTFOLIO: 300_000,
} as const;
