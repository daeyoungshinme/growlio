import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      getSession: vi.fn(() => Promise.resolve({ data: { session: null } })),
    },
  },
}));

const checkAuthMock = vi.fn();
vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector) => {
    const state = { checkAuth: checkAuthMock };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

import AuthCallbackPage from "@/pages/AuthCallbackPage";
import { supabase } from "@/lib/supabase";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/dashboard" element={<div>대시보드</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("AuthCallbackPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    checkAuthMock.mockResolvedValue(undefined);
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: null },
    } as never);
    vi.mocked(supabase.auth.onAuthStateChange).mockImplementation(
      () =>
        ({
          data: { subscription: { unsubscribe: vi.fn() } },
        }) as never,
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("URL에 error 파라미터가 있으면 즉시 실패 화면을 보여준다", async () => {
    renderAt("/auth/callback?error=access_denied&error_description=Email+link+is+invalid");

    await waitFor(() => {
      expect(screen.getByText("Email link is invalid")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /로그인으로 이동/ })).toHaveAttribute("href", "/login");
    expect(checkAuthMock).not.toHaveBeenCalled();
  });

  it("SIGNED_IN 이벤트를 받으면 checkAuth 후 성공 화면을 보여준다", async () => {
    vi.mocked(supabase.auth.onAuthStateChange).mockImplementation(((
      callback: (event: string) => void,
    ) => {
      callback("SIGNED_IN");
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    }) as never);

    renderAt("/auth/callback");

    await waitFor(() => {
      expect(screen.getByText(/이메일 인증이 완료되었습니다/)).toBeInTheDocument();
    });
    expect(checkAuthMock).toHaveBeenCalled();
  });

  it("마운트 시점에 이미 세션이 있으면 checkAuth 후 성공 화면을 보여준다", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValue({
      data: { session: { user: { id: "user-1" } } },
    } as never);

    renderAt("/auth/callback");

    await waitFor(() => {
      expect(screen.getByText(/이메일 인증이 완료되었습니다/)).toBeInTheDocument();
    });
    expect(checkAuthMock).toHaveBeenCalled();
  });

  it("세션도 에러도 감지되지 않으면 확인 중 화면을 보여준다", () => {
    renderAt("/auth/callback");
    expect(screen.getByText(/이메일 인증을 확인하는 중입니다/)).toBeInTheDocument();
  });

  it("5초 내에 세션도 에러도 감지되지 않으면 타임아웃 실패 화면을 보여준다", async () => {
    vi.useFakeTimers();
    renderAt("/auth/callback");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(screen.getByText(/이 기기에서 인증을 완료할 수 없습니다/)).toBeInTheDocument();
    expect(checkAuthMock).not.toHaveBeenCalled();
  });
});
