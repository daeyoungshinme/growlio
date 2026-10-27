import { QueryClient } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import {
  PersistQueryClientProvider,
  removeOldestQuery,
} from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
import {
  STALE_TIME,
  PERSIST_CACHE_BUSTER,
  PERSIST_CACHE_KEY,
  FOCUS_REFETCH_MIN_AGE,
  shouldPersistQuery,
} from "./constants/queryConfig";
import { getLocalStorageOrUndefined } from "./utils/safeStorage";
import { QUERY_KEYS } from "./constants/queryKeys";
import { setupServiceWorker } from "./lib/serviceWorker";
import { initSentryDeferred } from "./lib/sentry";

setupServiceWorker();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_TIME.SHORT,
      retry: 1,
      gcTime: 30 * 60 * 1000,
      refetchIntervalInBackground: false,
      // window focus(앱 복귀) 시 5분 이내 갱신된 쿼리는 재조회 생략 — 60초였을 땐 잠깐 다른 앱을 보고 돌아올 때마다
      // 현재 화면의 쿼리 8~10개가 한꺼번에 재요청됐다. 즉시 최신값이 필요하면 당겨서 새로고침을 쓴다.
      refetchOnWindowFocus: (query) =>
        Date.now() - (query.state.dataUpdatedAt ?? 0) > FOCUS_REFETCH_MIN_AGE,
    },
  },
});

// 계좌 목록은 계좌 CRUD·sync 시 명시적으로 무효화되므로 오래 신선하게 둔다 — observer마다 30초~1시간이
// 섞여 있어(staleTime 미지정 → 기본 30초) 리밸런싱·자산 화면에 들어갈 때마다 거의 매번 재조회됐다.
queryClient.setQueryDefaults(QUERY_KEYS.accounts, { staleTime: STALE_TIME.FIVE_MINUTES });

// 앱 재시작 시 대시보드·포트폴리오·계좌 캐시를 즉시 표시하기 위한 persistence (24h TTL)
const persister = createSyncStoragePersister({
  // 사이트 데이터 차단 시 window.localStorage 접근 자체가 throw해 앱이 부팅조차 못 한다 — 캐시 없이 부팅
  storage: getLocalStorageOrUndefined(),
  key: PERSIST_CACHE_KEY,
  throttleTime: 2000,
  // localStorage 용량 초과(QuotaExceededError) 시 가장 오래된 쿼리부터 제거하고 재시도
  retry: removeOldestQuery,
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        buster: PERSIST_CACHE_BUSTER,
        maxAge: 24 * 60 * 60 * 1000,
        dehydrateOptions: {
          shouldDehydrateQuery: shouldPersistQuery,
        },
      }}
    >
      <App />
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </PersistQueryClientProvider>
  </React.StrictMode>,
);

// 첫 렌더를 먼저 — Sentry는 유휴 시간에 로드(lib/sentry.ts)
initSentryDeferred();
