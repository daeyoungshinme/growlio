import { describe, it, expect, vi, afterEach } from "vitest";
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";

vi.mock("@/lib/supabase", () => ({
  getSupabase: () =>
    Promise.resolve({
      auth: {
        getSession: () => Promise.resolve({ data: { session: null } }),
        onAuthStateChange: vi.fn(),
        refreshSession: vi.fn(),
      },
    }),
}));

const toast = vi.fn();
vi.mock("@/utils/toast", () => ({ toast }));

const { api, SERVER_ERROR_TOAST_INTERVAL_MS } = await import("@/api/client");

api.defaults.adapter = (config: InternalAxiosRequestConfig) => {
  const res: AxiosResponse = { data: {}, status: 503, statusText: "", headers: {}, config };
  return Promise.reject(new AxiosError("503", "ERR_BAD_RESPONSE", config, null, res));
};

describe("api client 5xx 토스트 (plans/156 B3)", () => {
  afterEach(() => vi.useRealTimers());

  it("동시에 여러 요청이 5xx여도 토스트는 한 장, 간격이 지나면 다시 띄운다", async () => {
    vi.useFakeTimers({ now: 1_000_000, toFake: ["Date"] });

    await Promise.allSettled([api.get("/a"), api.get("/b"), api.get("/c")]);
    expect(toast).toHaveBeenCalledTimes(1);

    vi.setSystemTime(1_000_000 + SERVER_ERROR_TOAST_INTERVAL_MS + 1);
    await Promise.allSettled([api.get("/a")]);
    expect(toast).toHaveBeenCalledTimes(2);
  });
});
