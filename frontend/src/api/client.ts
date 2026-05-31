import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { supabase } from "../lib/supabase";
import { toast } from "../utils/toast";

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
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
      config._retry = true;
      try {
        const {
          data: { session },
        } = await supabase.auth.refreshSession();
        if (session?.access_token) {
          config.headers["Authorization"] = `Bearer ${session.access_token}`;
          return api.request(config);
        }
      } catch {
        // 리프레시 실패 시 세션 만료 이벤트 발행 → App.tsx에서 logout() 처리
      }
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
