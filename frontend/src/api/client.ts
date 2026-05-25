import axios from "axios";
import type { InternalAxiosRequestConfig } from "axios";
import { toast } from "../utils/toast";

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

export const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
  withCredentials: true,
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const config = error.config as RetryableConfig | undefined;
    const isAuthEndpoint = config?.url?.startsWith("/auth/");

    if (error.response?.status === 401 && config && !config._retry && !isAuthEndpoint) {
      config._retry = true;
      try {
        await axios.post("/api/v1/auth/refresh", null, { withCredentials: true });
        return api.request(config);
      } catch {
        if (window.location.pathname !== "/login") {
          toast("세션이 만료되었습니다. 다시 로그인해 주세요.", "error");
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);
