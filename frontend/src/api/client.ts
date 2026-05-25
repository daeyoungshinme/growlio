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
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const config = error.config as RetryableConfig | undefined;

    if (error.response?.status === 401 && config && !config._retry) {
      const refresh = localStorage.getItem("refresh_token");
      if (refresh) {
        config._retry = true;
        try {
          const { data } = await axios.post("/api/v1/auth/refresh", { refresh_token: refresh });
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          config.headers.Authorization = `Bearer ${data.access_token}`;
          return api.request(config);
        } catch {
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          toast("세션이 만료되었습니다. 다시 로그인해 주세요.", "error");
          window.location.href = "/login";
        }
      } else {
        localStorage.removeItem("access_token");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);
