export const PERSIST_CACHE_KEY = "rq-persist-cache";

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
