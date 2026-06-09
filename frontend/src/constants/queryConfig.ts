export const PERSIST_CACHE_KEY = "rq-persist-cache";

export const STALE_TIME = {
  SHORT: 30_000,
  MEDIUM: 60_000,
  LONG: 1000 * 60 * 60,
  EXCHANGE_RATE: 5 * 60 * 1000,
} as const;

export const REFETCH_INTERVAL = {
  DASHBOARD: 300_000,
  PORTFOLIO: 300_000,
} as const;
