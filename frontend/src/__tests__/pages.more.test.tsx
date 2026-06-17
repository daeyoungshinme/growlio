import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";

// mocks must come before imports
vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector) => {
    const state = {
      forgotPassword: vi.fn(),
      findAccount: vi.fn(),
      resetPassword: vi.fn(),
    };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      onAuthStateChange: vi.fn(() => ({
        data: {
          subscription: { unsubscribe: vi.fn() },
        },
      })),
    },
  },
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import FindAccountPage from "@/pages/FindAccountPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import { useAuthStore } from "@/stores/authStore";
import { supabase } from "@/lib/supabase";
import { toast } from "@/utils/toast";
import type { AuthState } from "@/stores/authStore";

function renderWithRouter(element: React.ReactElement) {
  return render(<MemoryRouter>{element}</MemoryRouter>);
}

// ForgotPasswordPage tests
describe("ForgotPasswordPage", () => {
  let forgotPasswordMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    forgotPasswordMock = vi.fn();
    vi.mocked(useAuthStore).mockImplementation((selector: (s: AuthState) => unknown) => {
      const state = { forgotPassword: forgotPasswordMock } as unknown as AuthState;
      return typeof selector === "function" ? selector(state) : state;
    });
  });

  it("renders the form initially", () => {
    renderWithRouter(<ForgotPasswordPage />);
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /재설정 링크 발송/ })).toBeInTheDocument();
  });

  it("calls forgotPassword on submit with the entered email", async () => {
    forgotPasswordMock.mockResolvedValue(undefined);
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /재설정 링크 발송/ }).closest("form")!);
    await waitFor(() => {
      expect(forgotPasswordMock).toHaveBeenCalledWith("user@example.com");
    });
  });

  it("shows success message after submission", async () => {
    forgotPasswordMock.mockResolvedValue(undefined);
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /재설정 링크 발송/ }).closest("form")!);
    await waitFor(() => {
      expect(screen.getByText(/이메일을 확인해주세요/)).toBeInTheDocument();
    });
    // Form should no longer be visible
    expect(screen.queryByPlaceholderText("you@example.com")).not.toBeInTheDocument();
  });

  it("shows error message on API failure", async () => {
    forgotPasswordMock.mockRejectedValue(new Error("server error"));
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /재설정 링크 발송/ }).closest("form")!);
    await waitFor(() => {
      expect(screen.getByText(/요청 중 오류가 발생했습니다/)).toBeInTheDocument();
    });
  });

  it("shows loading button text while submitting", async () => {
    let resolveFn: (() => void) | undefined;
    forgotPasswordMock.mockReturnValue(
      new Promise<void>((resolve) => {
        resolveFn = resolve;
      }),
    );
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.submit(screen.getByRole("button", { name: /재설정 링크 발송/ }).closest("form")!);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /전송 중/ })).toBeInTheDocument();
    });
    resolveFn?.();
  });

  it("has a link to find-account page", () => {
    renderWithRouter(<ForgotPasswordPage />);
    expect(screen.getByRole("link", { name: /아이디 찾기/ })).toHaveAttribute(
      "href",
      "/find-account",
    );
  });

  it("has a link back to login page", () => {
    renderWithRouter(<ForgotPasswordPage />);
    expect(screen.getByRole("link", { name: /로그인으로 돌아가기/ })).toHaveAttribute(
      "href",
      "/login",
    );
  });
});

// FindAccountPage tests
describe("FindAccountPage", () => {
  let findAccountMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    findAccountMock = vi.fn();
    vi.mocked(useAuthStore).mockImplementation((selector: (s: AuthState) => unknown) => {
      const state = { findAccount: findAccountMock } as unknown as AuthState;
      return typeof selector === "function" ? selector(state) : state;
    });
  });

  it("renders form with disabled button initially", () => {
    renderWithRouter(<FindAccountPage />);
    expect(screen.getByPlaceholderText(/가입 시 사용한 이름/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /이메일 확인/ })).toBeDisabled();
  });

  it("enables the button when name is entered", () => {
    renderWithRouter(<FindAccountPage />);
    fireEvent.change(screen.getByPlaceholderText(/가입 시 사용한 이름/), {
      target: { value: "testuser" },
    });
    expect(screen.getByRole("button", { name: /이메일 확인/ })).not.toBeDisabled();
  });

  it("button stays disabled when only whitespace entered", () => {
    renderWithRouter(<FindAccountPage />);
    fireEvent.change(screen.getByPlaceholderText(/가입 시 사용한 이름/), {
      target: { value: "   " },
    });
    expect(screen.getByRole("button", { name: /이메일 확인/ })).toBeDisabled();
  });

  it("calls findAccount on submit", async () => {
    findAccountMock.mockResolvedValue("email found: user@example.com");
    renderWithRouter(<FindAccountPage />);
    fireEvent.change(screen.getByPlaceholderText(/가입 시 사용한 이름/), {
      target: { value: "testuser" },
    });
    fireEvent.submit(screen.getByPlaceholderText(/가입 시 사용한 이름/).closest("form")!);
    await waitFor(() => {
      expect(findAccountMock).toHaveBeenCalledWith("testuser");
    });
  });

  it("shows result message on success", async () => {
    findAccountMock.mockResolvedValue("email found: user@example.com");
    renderWithRouter(<FindAccountPage />);
    fireEvent.change(screen.getByPlaceholderText(/가입 시 사용한 이름/), {
      target: { value: "testuser" },
    });
    fireEvent.submit(screen.getByPlaceholderText(/가입 시 사용한 이름/).closest("form")!);
    await waitFor(() => {
      expect(screen.getByText("email found: user@example.com")).toBeInTheDocument();
    });
  });

  it("shows error message on API failure", async () => {
    findAccountMock.mockRejectedValue(new Error("not found"));
    renderWithRouter(<FindAccountPage />);
    fireEvent.change(screen.getByPlaceholderText(/가입 시 사용한 이름/), {
      target: { value: "testuser" },
    });
    fireEvent.submit(screen.getByPlaceholderText(/가입 시 사용한 이름/).closest("form")!);
    await waitFor(() => {
      expect(screen.getByText(/조회 중 오류가 발생했습니다/)).toBeInTheDocument();
    });
  });

  it("shows loading button text while submitting", async () => {
    let resolveFn: ((v: string) => void) | undefined;
    findAccountMock.mockReturnValue(
      new Promise<string>((resolve) => {
        resolveFn = resolve;
      }),
    );
    renderWithRouter(<FindAccountPage />);
    fireEvent.change(screen.getByPlaceholderText(/가입 시 사용한 이름/), {
      target: { value: "testuser" },
    });
    fireEvent.submit(screen.getByPlaceholderText(/가입 시 사용한 이름/).closest("form")!);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /조회 중/ })).toBeInTheDocument();
    });
    resolveFn?.("done");
  });

  it("has links to other auth pages", () => {
    renderWithRouter(<FindAccountPage />);
    expect(screen.getByRole("link", { name: /비밀번호 찾기/ })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
    expect(screen.getByRole("link", { name: /로그인으로 돌아가기/ })).toHaveAttribute(
      "href",
      "/login",
    );
  });
});

// ResetPasswordPage tests
describe("ResetPasswordPage", () => {
  let resetPasswordMock: ReturnType<typeof vi.fn>;
  let onAuthStateChangeMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    resetPasswordMock = vi.fn();
    vi.mocked(useAuthStore).mockImplementation((selector: (s: AuthState) => unknown) => {
      const state = { resetPassword: resetPasswordMock } as unknown as AuthState;
      return typeof selector === "function" ? selector(state) : state;
    });
    onAuthStateChangeMock = vi.fn(() => ({
      data: { subscription: { unsubscribe: vi.fn() } },
    }));
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(supabase.auth.onAuthStateChange).mockImplementation(onAuthStateChangeMock as any);
  });

  it("shows waiting screen when session not ready", () => {
    renderWithRouter(<ResetPasswordPage />);
    expect(screen.getByText(/비밀번호 재설정 링크를 확인 중입니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText("새 비밀번호")).not.toBeInTheDocument();
  });

  it("shows link back to forgot-password when not ready", () => {
    renderWithRouter(<ResetPasswordPage />);
    expect(screen.getByRole("link", { name: /비밀번호 찾기로 돌아가기/ })).toHaveAttribute(
      "href",
      "/forgot-password",
    );
  });

  it("shows the form after PASSWORD_RECOVERY event", async () => {
    onAuthStateChangeMock.mockImplementation((callback: (event: string) => void) => {
      callback("PASSWORD_RECOVERY");
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    vi.mocked(supabase.auth.onAuthStateChange).mockImplementation(onAuthStateChangeMock as any);
    renderWithRouter(<ResetPasswordPage />);
    await waitFor(() => {
      expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument();
    });
    expect(screen.getByLabelText("비밀번호 확인")).toBeInTheDocument();
  });

  describe("with form visible (PASSWORD_RECOVERY fired)", () => {
    beforeEach(() => {
      onAuthStateChangeMock.mockImplementation((callback: (event: string) => void) => {
        callback("PASSWORD_RECOVERY");
        return { data: { subscription: { unsubscribe: vi.fn() } } };
      });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      vi.mocked(supabase.auth.onAuthStateChange).mockImplementation(onAuthStateChangeMock as any);
    });

    it("shows error when password is less than 8 chars", async () => {
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "short" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "short" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(screen.getByText(/비밀번호는 8자 이상이어야 합니다/)).toBeInTheDocument();
      });
    });

    it("shows error when passwords do not match", async () => {
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "password123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "different123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(screen.getByText(/비밀번호가 일치하지 않습니다/)).toBeInTheDocument();
      });
    });

    it("shows success message on successful reset", async () => {
      resetPasswordMock.mockResolvedValue(undefined);
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "newpassword123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "newpassword123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(screen.getByText(/비밀번호가 변경되었습니다/)).toBeInTheDocument();
      });
    });

    it("shows generic error on API failure", async () => {
      resetPasswordMock.mockRejectedValue(new Error("update failed"));
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "newpassword123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "newpassword123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(screen.getByText(/비밀번호 변경에 실패했습니다/)).toBeInTheDocument();
      });
    });

    it("shows toast for weak_password error code", async () => {
      const weakErr = Object.assign(new Error("weak"), { code: "weak_password" });
      resetPasswordMock.mockRejectedValue(weakErr);
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "password123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "password123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith(expect.stringContaining("유출된 비밀번호"), "error");
      });
    });

    it("shows toast for 'should not be too common' error", async () => {
      resetPasswordMock.mockRejectedValue(new Error("Password should not be too common"));
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "password123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "password123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith(expect.stringContaining("유출된 비밀번호"), "error");
      });
    });

    it("shows loading button text while submitting", async () => {
      let resolveFn: (() => void) | undefined;
      resetPasswordMock.mockReturnValue(
        new Promise<void>((resolve) => {
          resolveFn = resolve;
        }),
      );
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "password123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "password123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /변경 중/ })).toBeInTheDocument();
      });
      resolveFn?.();
    });

    it("hides login link after successful reset", async () => {
      resetPasswordMock.mockResolvedValue(undefined);
      renderWithRouter(<ResetPasswordPage />);
      await waitFor(() => expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument());
      // Before submit
      expect(screen.getByRole("link", { name: /로그인으로 돌아가기/ })).toBeInTheDocument();
      fireEvent.change(screen.getByLabelText("새 비밀번호"), {
        target: { value: "newpassword123" },
      });
      fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
        target: { value: "newpassword123" },
      });
      fireEvent.submit(screen.getByLabelText("새 비밀번호").closest("form")!);
      await waitFor(() => {
        expect(screen.getByText(/비밀번호가 변경되었습니다/)).toBeInTheDocument();
      });
      // After success, !success && <link> so login link is hidden
      expect(screen.queryByRole("link", { name: /로그인으로 돌아가기/ })).not.toBeInTheDocument();
    });
  });
});
