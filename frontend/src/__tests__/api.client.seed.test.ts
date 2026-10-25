import { describe, it, expect, vi } from "vitest";
import type { AxiosResponse, InternalAxiosRequestConfig } from "axios";

// 모듈 로드 전에 저장 세션을 심는다 — client.ts가 import 시점에 토큰을 동기로 시드하는지 확인
localStorage.setItem(
  "sb-testref-auth-token",
  JSON.stringify({
    access_token: "stored-token",
    expires_at: Math.floor(Date.now() / 1000) + 3600,
    user: { id: "u1" },
  }),
);

// SDK는 영원히 로드되지 않는 것처럼 — 시드 토큰만으로 첫 요청이 나가야 한다
vi.mock("@/lib/supabase", () => ({ getSupabase: () => new Promise(() => {}) }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

const { api } = await import("@/api/client");

describe("api client 토큰 시드", () => {
  it("SDK 로드 전에도 저장된 유효 토큰으로 첫 요청을 보낸다", async () => {
    const seen: (string | undefined)[] = [];
    api.defaults.adapter = (config: InternalAxiosRequestConfig) => {
      seen.push(config.headers?.["Authorization"] as string | undefined);
      return Promise.resolve({
        data: {},
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    };

    await api.get("/dashboard");

    expect(seen).toEqual(["Bearer stored-token"]);
  });
});
