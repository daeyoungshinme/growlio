import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import RegisterPage from "@/pages/RegisterPage";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockRegister = vi.fn();

vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector) => {
    const state = { register: mockRegister };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

function fillForm(email: string, password: string, confirm: string) {
  fireEvent.change(screen.getByLabelText("이메일"), { target: { value: email } });
  fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: password } });
  fireEvent.change(screen.getByLabelText("비밀번호 확인"), { target: { value: confirm } });
}

function renderPage() {
  return render(<MemoryRouter><RegisterPage /></MemoryRouter>);
}

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRegister.mockResolvedValue(undefined);
  });

  it("회원가입 폼을 렌더링한다", () => {
    renderPage();
    expect(screen.getByText("Growlio")).toBeInTheDocument();
    expect(screen.getByLabelText("이메일")).toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호")).toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호 확인")).toBeInTheDocument();
  });

  it("비밀번호가 8자 미만이면 에러 메시지를 표시한다", async () => {
    renderPage();
    fillForm("a@b.com", "short", "short");
    fireEvent.submit(screen.getByRole("button", { name: /회원가입/ }));
    await waitFor(() =>
      expect(screen.getByText("비밀번호는 8자 이상이어야 합니다")).toBeInTheDocument()
    );
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it("비밀번호가 불일치하면 에러 메시지를 표시한다", async () => {
    renderPage();
    fillForm("a@b.com", "password123", "different123");
    fireEvent.submit(screen.getByRole("button", { name: /회원가입/ }));
    await waitFor(() =>
      expect(screen.getByText("비밀번호가 일치하지 않습니다")).toBeInTheDocument()
    );
  });

  it("회원가입 성공 시 /dashboard로 이동한다", async () => {
    renderPage();
    fillForm("user@example.com", "password123", "password123");
    fireEvent.submit(screen.getByRole("button", { name: /회원가입/ }));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/dashboard"));
  });

  it("이미 사용 중인 이메일이면 에러 메시지를 표시한다", async () => {
    mockRegister.mockRejectedValue(new Error("User already registered"));
    renderPage();
    fillForm("existing@example.com", "password123", "password123");
    fireEvent.submit(screen.getByRole("button", { name: /회원가입/ }));
    await waitFor(() =>
      expect(screen.getByText("이미 사용 중인 이메일입니다")).toBeInTheDocument()
    );
  });

  it("이메일 확인이 필요한 경우 안내 메시지를 표시한다", async () => {
    mockRegister.mockRejectedValue(new Error("EMAIL_CONFIRMATION_REQUIRED"));
    renderPage();
    fillForm("new@example.com", "password123", "password123");
    fireEvent.submit(screen.getByRole("button", { name: /회원가입/ }));
    await waitFor(() =>
      expect(screen.getByText(/인증 링크를 클릭/)).toBeInTheDocument()
    );
  });

  it("일반 오류 발생 시 에러 메시지를 표시한다", async () => {
    mockRegister.mockRejectedValue(new Error("Unknown error"));
    renderPage();
    fillForm("user@example.com", "password123", "password123");
    fireEvent.submit(screen.getByRole("button", { name: /회원가입/ }));
    await waitFor(() =>
      expect(screen.getByText("회원가입 중 오류가 발생했습니다")).toBeInTheDocument()
    );
  });
});
