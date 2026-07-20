import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      signInWithPassword: vi.fn(),
      updateUser: vi.fn(),
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

import ChangePasswordModal from "@/components/settings/ChangePasswordModal";
import { supabase } from "@/lib/supabase";
import { toast } from "@/utils/toast";
import { useAuthStore } from "@/stores/authStore";

function renderModal(onClose = vi.fn()) {
  render(<ChangePasswordModal onClose={onClose} />);
  return { onClose };
}

function fillForm(current: string, next: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("현재 비밀번호"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("새 비밀번호"), { target: { value: next } });
  fireEvent.change(screen.getByLabelText("새 비밀번호 확인"), { target: { value: confirm } });
}

describe("ChangePasswordModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      userId: "user-1",
      email: "user@example.com",
      needsPasswordReset: false,
    });
  });

  it("세 개의 비밀번호 입력 필드를 렌더링한다", () => {
    renderModal();
    expect(screen.getByLabelText("현재 비밀번호")).toBeInTheDocument();
    expect(screen.getByLabelText("새 비밀번호")).toBeInTheDocument();
    expect(screen.getByLabelText("새 비밀번호 확인")).toBeInTheDocument();
  });

  it("필드가 비어있으면 변경하기 버튼이 비활성화된다", () => {
    renderModal();
    expect(screen.getByRole("button", { name: "변경하기" })).toBeDisabled();
  });

  it("취소 버튼을 클릭하면 onClose가 호출된다", () => {
    const { onClose } = renderModal();
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("새 비밀번호가 8자 미만이면 에러를 표시한다", async () => {
    renderModal();
    fillForm("oldpass123", "short", "short");
    fireEvent.click(screen.getByRole("button", { name: "변경하기" }));
    await waitFor(() => {
      expect(screen.getByText("새 비밀번호는 8자 이상이어야 합니다.")).toBeInTheDocument();
    });
    expect(supabase.auth.signInWithPassword).not.toHaveBeenCalled();
  });

  it("새 비밀번호와 확인이 일치하지 않으면 에러를 표시한다", async () => {
    renderModal();
    fillForm("oldpass123", "newpass123", "newpass456");
    fireEvent.click(screen.getByRole("button", { name: "변경하기" }));
    await waitFor(() => {
      expect(screen.getByText("새 비밀번호가 일치하지 않습니다.")).toBeInTheDocument();
    });
  });

  it("성공 시 성공 토스트를 표시하고 모달을 닫는다", async () => {
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: { user: { id: "user-1" }, session: {} },
      error: null,
    } as never);
    vi.mocked(supabase.auth.updateUser).mockResolvedValue({ data: {}, error: null } as never);
    const { onClose } = renderModal();
    fillForm("oldpass123", "newpass123", "newpass123");
    fireEvent.click(screen.getByRole("button", { name: "변경하기" }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("비밀번호가 변경되었습니다", "success");
    });
    expect(onClose).toHaveBeenCalled();
  });

  it("현재 비밀번호가 틀리면 에러 문구를 표시한다", async () => {
    vi.mocked(supabase.auth.signInWithPassword).mockResolvedValue({
      data: { user: null, session: null },
      error: new Error("Invalid login credentials"),
    } as never);
    renderModal();
    fillForm("wrongpass", "newpass123", "newpass123");
    fireEvent.click(screen.getByRole("button", { name: "변경하기" }));

    await waitFor(() => {
      expect(screen.getByText("현재 비밀번호가 일치하지 않습니다.")).toBeInTheDocument();
    });
    expect(supabase.auth.updateUser).not.toHaveBeenCalled();
  });
});
