import { describe, it, expect, vi, beforeEach } from "vitest";

// ── mocks must come before imports ──
vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn(),
      getSession: vi.fn(),
      resetPasswordForEmail: vi.fn(),
      updateUser: vi.fn(),
    },
  },
}));

vi.mock("@/api/client", () => {
  const mockApi = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  };
  return {
    api: mockApi,
    apiGet: (url: string, ...args: unknown[]) =>
      mockApi.get(url, ...args).then((r: { data: unknown }) => r.data),
    apiPost: (url: string, ...args: unknown[]) =>
      mockApi.post(url, ...args).then((r: { data: unknown }) => r.data),
    apiPut: (url: string, ...args: unknown[]) =>
      mockApi.put(url, ...args).then((r: { data: unknown }) => r.data),
    apiPatch: (url: string, ...args: unknown[]) =>
      mockApi.patch(url, ...args).then((r: { data: unknown }) => r.data),
    apiDelete: (url: string, ...args: unknown[]) =>
      mockApi.delete(url, ...args).then((r: { data: unknown }) => r.data),
  };
});

import { supabase } from "@/lib/supabase";
import { api } from "@/api/client";

// We test the store by calling its actions directly
// Re-import fresh store state per test by resetting the module
async function getStore() {
  const { useAuthStore } = await import("@/stores/authStore");
  return useAuthStore.getState();
}

describe("authStore — login", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("로그인 성공 시 isAuthenticated=true와 이메일을 설정한다", async () => {
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: {
        user: { id: "user-1", email: "user@example.com" },
        session: { access_token: "token" },
      },
      error: null,
    } as never);
    vi.mocked(api.post).mockResolvedValue({ data: {} });

    const store = await getStore();
    await store.login("user@example.com", "password123");

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.email).toBe("user@example.com");
    expect(state.userId).toBe("user-1");
  });

  it("로그인 실패 시 에러를 던진다", async () => {
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: { user: null, session: null },
      error: { message: "Invalid credentials" },
    } as never);

    const store = await getStore();
    await expect(store.login("bad@example.com", "wrong")).rejects.toThrow("Invalid credentials");
  });

  it("sync-profile 호출 실패해도 로그인은 계속 진행된다", async () => {
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: {
        user: { id: "user-2", email: "user2@example.com" },
        session: { access_token: "token" },
      },
      error: null,
    } as never);
    vi.mocked(api.post).mockRejectedValue(new Error("backend down"));

    const store = await getStore();
    // Should not throw even though sync-profile fails
    await expect(store.login("user2@example.com", "pass123")).resolves.not.toThrow();
  });
});

describe("authStore — register", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("이메일 인증 필요 시 EMAIL_CONFIRMATION_REQUIRED를 던진다", async () => {
    vi.mocked(supabase.auth.signUp).mockResolvedValue({
      data: {
        user: { id: "user-3", email: "new@example.com" },
        session: null, // no session = email confirmation needed
      },
      error: null,
    } as never);

    const store = await getStore();
    await expect(store.register("new@example.com", "password123")).rejects.toThrow(
      "EMAIL_CONFIRMATION_REQUIRED",
    );
  });

  it("세션이 있으면 sync-profile 호출 후 isAuthenticated=true", async () => {
    vi.mocked(supabase.auth.signUp).mockResolvedValue({
      data: {
        user: { id: "user-4", email: "confirmed@example.com" },
        session: { access_token: "token" },
      },
      error: null,
    } as never);
    vi.mocked(api.post).mockResolvedValue({ data: {} });

    const store = await getStore();
    await store.register("confirmed@example.com", "password123", "테스트 유저");

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.email).toBe("confirmed@example.com");
  });

  it("supabase 오류 시 에러를 던진다", async () => {
    vi.mocked(supabase.auth.signUp).mockResolvedValue({
      data: { user: null, session: null },
      error: { message: "Email already in use" },
    } as never);

    const store = await getStore();
    await expect(store.register("dup@example.com", "password123")).rejects.toThrow(
      "Email already in use",
    );
  });

  it("displayName 없이 register 호출 시 display_name이 null로 전송된다", async () => {
    vi.mocked(supabase.auth.signUp).mockResolvedValue({
      data: {
        user: { id: "user-5", email: "u@example.com" },
        session: { access_token: "token" },
      },
      error: null,
    } as never);
    vi.mocked(api.post).mockResolvedValue({ data: {} });

    const store = await getStore();
    await store.register("u@example.com", "password123");
    expect(api.post).toHaveBeenCalledWith("/auth/sync-profile", { display_name: null });
  });
});

describe("authStore — logout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("로그아웃 시 isAuthenticated=false가 된다", async () => {
    vi.mocked(supabase.auth.signOut).mockResolvedValue({ error: null } as never);

    const store = await getStore();
    await store.logout();

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.userId).toBe(null);
    expect(state.email).toBe(null);
  });
});

describe("authStore — checkAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("세션 없으면 isAuthenticated=false가 된다", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: null },
      error: null,
    } as never);

    const store = await getStore();
    await store.checkAuth();

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isAuthChecking).toBe(false);
  });

  it("세션 있고 /auth/me 성공 시 isAuthenticated=true", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: {
        session: {
          user: { id: "user-6", email: "active@example.com" },
          access_token: "token",
        },
      },
      error: null,
    } as never);
    vi.mocked(api.get).mockResolvedValue({
      data: { needs_password_reset: false },
    });

    const store = await getStore();
    await store.checkAuth();

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
  });

  it("세션 있고 /auth/me가 401이면 sync-profile 후 재시도한다", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: {
        session: {
          user: { id: "user-7", email: "new-verified@example.com" },
          access_token: "token",
        },
      },
      error: null,
    } as never);
    // First call to /auth/me returns 401
    const authError = { response: { status: 401 } };
    vi.mocked(api.get)
      .mockRejectedValueOnce(authError)
      .mockResolvedValueOnce({ data: { needs_password_reset: false } });
    vi.mocked(api.post).mockResolvedValue({ data: {} });

    const store = await getStore();
    await store.checkAuth();

    expect(api.post).toHaveBeenCalledWith("/auth/sync-profile", { display_name: null });
    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
  });

  it("세션 있고 /auth/me가 401이고 sync-profile도 실패 시 로그아웃된다", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: {
        session: {
          user: { id: "user-8", email: "fail@example.com" },
          access_token: "token",
        },
      },
      error: null,
    } as never);
    const authError = { response: { status: 401 } };
    vi.mocked(api.get).mockRejectedValue(authError);
    vi.mocked(api.post).mockRejectedValue(new Error("sync failed"));

    const store = await getStore();
    await store.checkAuth();

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
  });

  it("세션 있고 /auth/me가 비-401 오류이면 로그아웃된다", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: {
        session: {
          user: { id: "user-9", email: "error@example.com" },
          access_token: "token",
        },
      },
      error: null,
    } as never);
    vi.mocked(api.get).mockRejectedValue({ response: { status: 500 } });

    const store = await getStore();
    await store.checkAuth();

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
  });

  it("needs_password_reset=true이면 needsPasswordReset이 true가 된다", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: {
        session: {
          user: { id: "user-10", email: "reset@example.com" },
          access_token: "token",
        },
      },
      error: null,
    } as never);
    vi.mocked(api.get).mockResolvedValue({ data: { needs_password_reset: true } });

    const store = await getStore();
    await store.checkAuth();

    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.needsPasswordReset).toBe(true);
  });
});

describe("authStore — findAccount", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("이름으로 계정을 찾으면 메시지를 반환한다", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { message: "가입된 이메일: user@example.com" } });
    const store = await getStore();
    const msg = await store.findAccount("홍길동");
    expect(api.post).toHaveBeenCalledWith("/auth/find-account", { display_name: "홍길동" });
    expect(msg).toBe("가입된 이메일: user@example.com");
  });
});

describe("authStore — forgotPassword", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("성공 시 에러를 던지지 않는다", async () => {
    vi.mocked(supabase.auth.resetPasswordForEmail).mockResolvedValue({
      data: {},
      error: null,
    } as never);
    const store = await getStore();
    await expect(store.forgotPassword("user@example.com")).resolves.not.toThrow();
  });

  it("supabase 오류 시 에러를 던진다", async () => {
    vi.mocked(supabase.auth.resetPasswordForEmail).mockResolvedValue({
      data: {},
      error: new Error("rate limited"),
    } as never);
    const store = await getStore();
    await expect(store.forgotPassword("user@example.com")).rejects.toThrow("rate limited");
  });
});

describe("authStore — resetPassword", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("성공 시 needsPasswordReset=false가 된다", async () => {
    vi.mocked(supabase.auth.updateUser).mockResolvedValue({ data: {}, error: null } as never);
    const store = await getStore();
    await store.resetPassword("newpass123");
    const state = (await import("@/stores/authStore")).useAuthStore.getState();
    expect(state.needsPasswordReset).toBe(false);
  });

  it("supabase 오류 시 에러를 던진다", async () => {
    vi.mocked(supabase.auth.updateUser).mockResolvedValue({
      data: { user: null },
      error: new Error("update failed"),
    } as never);
    const store = await getStore();
    await expect(store.resetPassword("badpass")).rejects.toThrow("update failed");
  });
});
