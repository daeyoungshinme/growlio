import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/auth", () => ({
  deleteAccount: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signOut: vi.fn().mockResolvedValue({ error: null }),
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    },
  },
}));

vi.mock("@/api/client", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), patch: vi.fn() },
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

import DeleteAccountModal from "@/components/settings/DeleteAccountModal";
import { deleteAccount } from "@/api/auth";
import { supabase } from "@/lib/supabase";
import { toast } from "@/utils/toast";
import { useAuthStore } from "@/stores/authStore";

function renderModal(onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const clearSpy = vi.spyOn(qc, "clear");
  render(
    <QueryClientProvider client={qc}>
      <DeleteAccountModal onClose={onClose} />
    </QueryClientProvider>,
  );
  return { onClose, clearSpy };
}

describe("DeleteAccountModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      userId: "user-1",
      email: "user@example.com",
      needsPasswordReset: false,
    });
  });

  it("경고 문구와 비밀번호 입력 필드를 렌더링한다", () => {
    renderModal();
    expect(screen.getByText(/영구적으로/)).toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호 확인")).toBeInTheDocument();
  });

  it("비밀번호를 입력하지 않으면 탈퇴하기 버튼이 비활성화된다", () => {
    renderModal();
    expect(screen.getByRole("button", { name: /탈퇴하기/ })).toBeDisabled();
  });

  it("취소 버튼을 클릭하면 onClose가 호출된다", () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("탈퇴 성공 시 세션을 정리하고 인증 상태를 초기화한다", async () => {
    vi.mocked(deleteAccount).mockResolvedValue(undefined);
    const { onClose, clearSpy } = renderModal();

    fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
      target: { value: "correct-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /탈퇴하기/ }));

    await waitFor(() => {
      expect(deleteAccount).toHaveBeenCalledWith("correct-password");
    });
    await waitFor(() => {
      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });
    expect(clearSpy).toHaveBeenCalled();
    expect(supabase.auth.signOut).toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith("회원 탈퇴가 완료되었습니다", "success");
    expect(onClose).toHaveBeenCalled();
  });

  it("탈퇴 실패 시 에러 토스트를 표시하고 로그인 상태를 유지한다", async () => {
    vi.mocked(deleteAccount).mockRejectedValue({
      response: { data: { detail: "비밀번호가 올바르지 않습니다" } },
    });
    renderModal();

    fireEvent.change(screen.getByLabelText("비밀번호 확인"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /탈퇴하기/ }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("비밀번호가 올바르지 않습니다", "error");
    });
    expect(useAuthStore.getState().isAuthenticated).toBe(true);
  });
});
