import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { supabase } from "../lib/supabase";
import { toast } from "../utils/toast";

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

type QueueEntry = { resolve: (token: string) => void; reject: (err: unknown) => void };

let isRefreshing = false;
let failedQueue: QueueEntry[] = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((p) => (error ? p.reject(error) : p.resolve(token!)));
  failedQueue = [];
}

export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  timeout: 60_000,
});

// Supabase 액세스 토큰을 Authorization 헤더에 첨부
api.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (session?.access_token) {
    config.headers["Authorization"] = `Bearer ${session.access_token}`;
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
          config.headers["Authorization"] = `Bearer ${token}`;
          return api.request(config);
        });
      }

      config._retry = true;
      isRefreshing = true;

      try {
        const {
          data: { session },
        } = await supabase.auth.refreshSession();
        if (session?.access_token) {
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
  }
);
