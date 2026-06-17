import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      signInWithPassword: vi.fn(),
      signUp: vi.fn(),
      signOut: vi.fn().mockResolvedValue({}),
      resetPasswordForEmail: vi.fn(),
      updateUser: vi.fn(),
    },
  },
}));

vi.mock("@/api/client", () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}));

vi.mock("@/utils/error", () => ({
  getHttpStatus: vi.fn(),
}));

describe("useThemeStore", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    // Reset the store module between tests
    vi.resetModules();
  });

  it("초기 상태가 localStorage 값에 따라 설정된다 (dark)", async () => {
    localStorage.setItem("theme", "dark");
    const { useThemeStore } = await import("@/stores/themeStore");
    const store = useThemeStore.getState();
    expect(store.isDark).toBe(true);
  });

  it("초기 상태가 localStorage 값에 따라 설정된다 (light)", async () => {
    localStorage.setItem("theme", "light");
    const { useThemeStore } = await import("@/stores/themeStore");
    const store = useThemeStore.getState();
    expect(store.isDark).toBe(false);
  });

  it("toggle이 isDark를 반전시키고 localStorage를 업데이트한다", async () => {
    localStorage.setItem("theme", "light");
    const { useThemeStore } = await import("@/stores/themeStore");
    const store = useThemeStore.getState();
    store.toggle();
    expect(useThemeStore.getState().isDark).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("toggle을 두 번 호출하면 원래 상태로 돌아온다", async () => {
    localStorage.setItem("theme", "dark");
    const { useThemeStore } = await import("@/stores/themeStore");
    const initialDark = useThemeStore.getState().isDark;
    useThemeStore.getState().toggle();
    useThemeStore.getState().toggle();
    expect(useThemeStore.getState().isDark).toBe(initialDark);
  });
});

describe("useAuthStore", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    // Reset zustand store state
    const { useAuthStore } = await import("@/stores/authStore");
    useAuthStore.setState({
      isAuthenticated: false,
      isAuthChecking: true,
      userId: null,
      email: null,
      needsPasswordReset: false,
    });
  });

  it("초기 상태는 비인증 상태다", async () => {
    const { useAuthStore } = await import("@/stores/authStore");
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isAuthChecking).toBe(true);
    expect(state.userId).toBeNull();
  });

  it("login이 성공하면 isAuthenticated가 true가 된다", async () => {
    const { supabase } = await import("@/lib/supabase");
    const { api } = await import("@/api/client");
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: { user: { id: "user-1", email: "test@example.com" }, session: null },
      error: null,
    } as any);
    vi.mocked(api.post).mockResolvedValue({});

    const { useAuthStore } = await import("@/stores/authStore");
    await useAuthStore.getState().login("test@example.com", "password");

    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().email).toBe("test@example.com");
  });

  it("login이 실패하면 에러를 throw한다", async () => {
    const { supabase } = await import("@/lib/supabase");
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: { user: null, session: null },
      error: { message: "Invalid credentials" },
    } as any);

    const { useAuthStore } = await import("@/stores/authStore");
    await expect(useAuthStore.getState().login("test@example.com", "wrong")).rejects.toThrow(
      "Invalid credentials",
    );
  });

  it("logout이 상태를 초기화한다", async () => {
    const { useAuthStore } = await import("@/stores/authStore");
    useAuthStore.setState({ isAuthenticated: true, userId: "user-1", email: "test@example.com" });

    const { supabase } = await import("@/lib/supabase");
    vi.mocked(supabase.auth.signOut).mockResolvedValue({ error: null });

    await useAuthStore.getState().logout();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().userId).toBeNull();
  });

  it("checkAuth가 세션 없을 때 로그아웃 상태로 설정한다", async () => {
    const { supabase } = await import("@/lib/supabase");
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: null },
    } as any);

    const { useAuthStore } = await import("@/stores/authStore");
    await useAuthStore.getState().checkAuth();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useAuthStore.getState().isAuthChecking).toBe(false);
  });

  it("checkAuth가 세션 있을 때 인증 상태로 설정한다", async () => {
    const { supabase } = await import("@/lib/supabase");
    const { api } = await import("@/api/client");
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: {
        session: { user: { id: "user-1", email: "test@example.com" } },
      },
    } as any);
    vi.mocked(api.get).mockResolvedValue({
      data: { needs_password_reset: false },
    });

    const { useAuthStore } = await import("@/stores/authStore");
    await useAuthStore.getState().checkAuth();
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
    expect(useAuthStore.getState().isAuthChecking).toBe(false);
  });

  it("findAccount가 API 응답을 반환한다", async () => {
    const { api } = await import("@/api/client");
    vi.mocked(api.post).mockResolvedValue({ data: { message: "계정을 찾았습니다" } });

    const { useAuthStore } = await import("@/stores/authStore");
    const msg = await useAuthStore.getState().findAccount("홍길동");
    expect(msg).toBe("계정을 찾았습니다");
  });

  it("forgotPassword가 이메일을 전송한다", async () => {
    const { supabase } = await import("@/lib/supabase");
    vi.mocked(supabase.auth.resetPasswordForEmail).mockResolvedValue({
      data: {},
      error: null,
    } as never);

    const { useAuthStore } = await import("@/stores/authStore");
    await expect(
      useAuthStore.getState().forgotPassword("test@example.com"),
    ).resolves.toBeUndefined();
  });

  it("forgotPassword가 실패하면 에러를 throw한다", async () => {
    const { supabase } = await import("@/lib/supabase");
    vi.mocked(supabase.auth.resetPasswordForEmail).mockResolvedValue({
      data: null,
      error: new Error("Email not found"),
    } as any);

    const { useAuthStore } = await import("@/stores/authStore");
    await expect(useAuthStore.getState().forgotPassword("unknown@example.com")).rejects.toThrow();
  });

  it("resetPassword가 성공하면 needsPasswordReset을 false로 설정한다", async () => {
    const { supabase } = await import("@/lib/supabase");
    vi.mocked(supabase.auth.updateUser).mockResolvedValue({ data: {}, error: null } as never);

    const { useAuthStore } = await import("@/stores/authStore");
    useAuthStore.setState({ needsPasswordReset: true });
    await useAuthStore.getState().resetPassword("newpassword123");
    expect(useAuthStore.getState().needsPasswordReset).toBe(false);
  });
});
