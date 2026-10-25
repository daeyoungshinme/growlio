import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/supabase", () => ({ getSupabase: () => new Promise(() => {}) }));
vi.mock("@/api/client", () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const HOUR = 60 * 60 * 1000;

function seed(cachedAgoMs: number, sessionUser = "u1") {
  localStorage.setItem(
    "growlio:auth-me",
    JSON.stringify({ userId: "u1", needsPasswordReset: false, cachedAt: Date.now() - cachedAgoMs }),
  );
  localStorage.setItem(
    "sb-testref-auth-token",
    JSON.stringify({
      access_token: "t",
      expires_at: Math.floor(Date.now() / 1000) - 60, // 만료돼도 refresh_token으로 복원 가능
      user: { id: sessionUser },
    }),
  );
}

async function initialState() {
  vi.resetModules();
  const { useAuthStore } = await import("@/stores/authStore");
  return useAuthStore.getState();
}

describe("authStore 낙관적 인증", () => {
  beforeEach(() => localStorage.clear());

  it("/auth/me 캐시가 30분을 넘어도 7일 이내면 검증을 기다리지 않는다", async () => {
    seed(5 * HOUR);
    const s = await initialState();
    expect(s.isAuthChecking).toBe(false);
    expect(s.isAuthenticated).toBe(true);
  });

  it("7일이 지나면 검증을 기다린다", async () => {
    seed(8 * 24 * HOUR);
    const s = await initialState();
    expect(s.isAuthChecking).toBe(true);
    expect(s.isAuthenticated).toBe(false);
  });

  it("저장 세션의 사용자가 캐시와 다르면 낙관적 로그인하지 않는다", async () => {
    seed(5 * HOUR, "other");
    const s = await initialState();
    expect(s.isAuthChecking).toBe(true);
  });

  it("저장 세션이 없으면 낙관적 로그인하지 않는다", async () => {
    seed(5 * HOUR);
    localStorage.removeItem("sb-testref-auth-token");
    const s = await initialState();
    expect(s.isAuthenticated).toBe(false);
  });
});
