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
  PERSIST_QUERY_KEYS,
  shouldPersistQuery,
} from "./constants/queryConfig";
import { getLocalStorageOrUndefined } from "./utils/safeStorage";
import { removeLegacyDeviceKeys } from "./constants/storageKeys";
import { setupPreloadErrorReload, setupServiceWorker } from "./lib/serviceWorker";
import { initSentryDeferred } from "./lib/sentry";
import { readValidStoredToken } from "./lib/storedSession";
import { prefetchDashboardData } from "./api/prefetch";
import { shouldRetryQuery, retryDelayMs } from "./api/retryPolicy";

setupServiceWorker();
setupPreloadErrorReload();
removeLegacyDeviceKeys();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_TIME.SHORT,
      // 4xx(권한·검증)는 다시 보내도 같다 — 네트워크 오류·5xx·타임아웃만 1회. 잠든 Render가 깨는 동안 홈 쿼리
      // 10여 개가 60초 타임아웃 후 동시에 재시도하던 걸 백오프로 흩는다(plans/125 C7)
      retry: shouldRetryQuery,
      retryDelay: retryDelayMs,
      gcTime: 30 * 60 * 1000,
      refetchIntervalInBackground: false,
      // window focus(앱 복귀) 시 5분 이내 갱신된 쿼리는 재조회 생략 — 60초였을 땐 잠깐 다른 앱을 보고 돌아올 때마다
      // 현재 화면의 쿼리 8~10개가 한꺼번에 재요청됐다. 즉시 최신값이 필요하면 당겨서 새로고침을 쓴다.
      refetchOnWindowFocus: (query) =>
        Date.now() - (query.state.dataUpdatedAt ?? 0) > FOCUS_REFETCH_MIN_AGE,
    },
  },
});

// persist 대상은 gcTime을 maxAge(24h)와 맞춘다 — 기본 30분이면 다른 탭에 머무는 동안(또는 WebView가 백그라운드에
// 살아 있는 동안) 관찰자 없는 홈 쿼리가 지워지고, persister가 그 상태를 저장해 다음 콜드 스타트가 빈 화면이 됐다
// setQueryDefaults는 프리픽스로 맞추므로 goal-recommendation은 persist하는 overall만 — 기간별·연령대·중복 분석
// 변형까지 하루 동안 메모리에 남기지 않는다(shouldPersistQuery와 같은 범위, plans/126 C5)
for (const key of PERSIST_QUERY_KEYS) {
  const prefix = key === "goal-recommendation" ? [key, "overall"] : [key];
  queryClient.setQueryDefaults(prefix, { gcTime: STALE_TIME.DAY });
}

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
      // 복원 직후 저장 토큰이 유효하면 바로 홈 데이터를 받기 시작한다 — 예전엔 Supabase SDK(약 200KB) 로드와 getSession을
      // 기다린 뒤에야 시작했다(plans/125 C3). 복원된 신선한 쿼리는 prefetch가 건너뛰고, checkAuth의 같은 호출은 dedupe된다
      onSuccess={() => {
        if (readValidStoredToken()) prefetchDashboardData(queryClient);
      }}
    >
      <App />
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </PersistQueryClientProvider>
  </React.StrictMode>,
);

// 첫 렌더를 먼저 — Sentry는 유휴 시간에 로드(lib/sentry.ts)
initSentryDeferred();
