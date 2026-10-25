import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { getSupabase } from "@/lib/supabase";
import { hasStoredSession, readValidStoredToken } from "@/lib/storedSession";
import { toast } from "@/utils/toast";
import { getApiBaseUrl } from "@/utils/platform";

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

type QueueEntry = { resolve: (token: string) => void; reject: (err: unknown) => void };

let isRefreshing = false;
let failedQueue: QueueEntry[] = [];
// 세션 토큰 캐시 — 매 요청마다 getSession() 호출을 피하기 위해 모듈 레벨에서 관리.
// 저장된 세션이 아직 유효하면 SDK 로드 전에 동기로 채운다 — 비워 두면 부팅 직후 요청이 헤더 없이
// 나가 401 → refreshSession → 재시도 왕복이 생겼다.
let cachedToken: string | null = readValidStoredToken();

// 앱 시작 시 현재 세션 토큰 초기화 + 로그인·로그아웃·토큰 갱신 시 캐시 자동 갱신.
// getSupabase()가 @supabase/supabase-js를 동적 import하므로 이 초기화는 지연된다.
const initialTokenReady: Promise<void> = getSupabase()
  .then(async (supabase) => {
    supabase.auth.onAuthStateChange((_event, session) => {
      cachedToken = session?.access_token ?? null;
    });
    try {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      cachedToken = session?.access_token ?? null;
    } catch {
      /* 세션 조회 실패 — 요청은 헤더 없이 나가고 401 경로가 처리 */
    }
  })
  .catch(() => {
    /* SDK 청크 로드 실패 — 위와 동일하게 401 경로로 폴백 */
  });
let initialTokenSettled = false;
void initialTokenReady.finally(() => {
  initialTokenSettled = true;
});

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  failedQueue = [];
}

export const api = axios.create({
  // 네이티브 앱: VITE_API_DOMAIN 기반 절대 URL, 웹(PWA/dev): /api/v1 (상대 경로 — Vite 프록시 또는 nginx 처리)
  baseURL: `${getApiBaseUrl()}/api/v1`,
  headers: { "Content-Type": "application/json" },
  timeout: 60_000,
});

// Supabase 액세스 토큰을 Authorization 헤더에 첨부 (캐시된 토큰 사용)
api.interceptors.request.use(async (config) => {
  // 저장 세션이 있는데 토큰이 만료돼 시드되지 않았다면 SDK의 세션 복원(갱신)을 한 번 기다린다.
  // 로그인 전(저장 세션 없음) 요청은 기다리지 않는다.
  if (!cachedToken && !initialTokenSettled && hasStoredSession()) {
    await initialTokenReady;
  }
  if (cachedToken) {
    config.headers["Authorization"] = `Bearer ${cachedToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const config = error.config as RetryableConfig | undefined;
    const isAuthEndpoint = config?.url?.startsWith("/auth/");
    const status = error.response?.status as number | undefined;

    if (status === 401 && config && !config._retry && !isAuthEndpoint) {
      // 이미 refresh 중이면 큐에 등록하고 refresh 완료 후 재시도
      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          // 재시도도 _retry를 달아야 새 토큰으로 다시 401이면 갱신을 또 시작하지 않고 실패로 끝난다
          config._retry = true;
          config.headers["Authorization"] = `Bearer ${token}`;
          return api.request(config);
        });
      }

      config._retry = true;
      isRefreshing = true;

      try {
        const supabase = await getSupabase();
        const {
          data: { session },
        } = await supabase.auth.refreshSession();
        if (session?.access_token) {
          cachedToken = session.access_token; // onAuthStateChange보다 먼저 캐시 갱신
          config.headers["Authorization"] = `Bearer ${session.access_token}`;
          processQueue(null, session.access_token);
          return api.request(config);
        }
        processQueue(error);
      } catch (refreshError) {
        processQueue(refreshError);
      } finally {
        isRefreshing = false;
      }

      // refresh 실패 또는 세션 없음 → 로그아웃 처리
      if (window.location.pathname !== "/login") {
        toast("세션이 만료되었습니다. 다시 로그인해 주세요.", "error");
        window.dispatchEvent(new CustomEvent("growlio:session-expired"));
      }
    } else if (status != null && status >= 500 && !isAuthEndpoint) {
      toast("서버 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", "error");
    }

    return Promise.reject(error);
  },
);

type ApiConfig = Parameters<typeof api.get>[1];

export const apiGet = <T>(url: string, config?: ApiConfig) =>
  api.get<T>(url, config).then((r) => r.data);

export const apiPost = <T>(url: string, data?: unknown, config?: ApiConfig) =>
  api.post<T>(url, data, config).then((r) => r.data);

export const apiPut = <T>(url: string, data?: unknown, config?: ApiConfig) =>
  api.put<T>(url, data, config).then((r) => r.data);

export const apiPatch = <T>(url: string, data?: unknown, config?: ApiConfig) =>
  api.patch<T>(url, data, config).then((r) => r.data);

export const apiDelete = <T = unknown>(url: string, config?: ApiConfig) =>
  api.delete<T>(url, config).then((r) => r.data);
