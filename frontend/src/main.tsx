import * as Sentry from "@sentry/react";
import { QueryClient } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import { STALE_TIME, PERSIST_CACHE_KEY } from "./constants/queryConfig";

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined;
if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.MODE,
    release: import.meta.env.VITE_SENTRY_RELEASE as string | undefined,
    integrations: [Sentry.browserTracingIntegration()],
    tracesSampleRate: 0.1,
  });
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_TIME.SHORT,
      retry: 1,
      gcTime: 30 * 60 * 1000,
      refetchIntervalInBackground: false,
      // window focus 시 60초 이내 갱신된 쿼리는 재조회 생략 (thundering herd 방지)
      refetchOnWindowFocus: (query) =>
        Date.now() - (query.state.dataUpdatedAt ?? 0) > 60_000,
    },
  },
});

// 앱 재시작 시 대시보드·포트폴리오·계좌 캐시를 즉시 표시하기 위한 persistence (24h TTL)
const persister = createSyncStoragePersister({
  storage: typeof window !== "undefined" ? window.localStorage : undefined,
  key: PERSIST_CACHE_KEY,
  throttleTime: 2000,
});

const PERSIST_QUERY_KEYS = new Set(["dashboard", "portfolio-overview", "accounts", "dca-analysis"]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        buster: "v1",
        maxAge: 24 * 60 * 60 * 1000,
        dehydrateOptions: {
          shouldDehydrateQuery: (query) =>
            PERSIST_QUERY_KEYS.has(query.queryKey[0] as string),
        },
      }}
    >
      <App />
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </PersistQueryClientProvider>
  </React.StrictMode>
);
