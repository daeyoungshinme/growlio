import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LoginPage from "@/pages/LoginPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import FindAccountPage from "@/pages/FindAccountPage";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockLogin = vi.fn();
const mockForgotPassword = vi.fn();
const mockFindAccount = vi.fn();

vi.mock("@/api/dashboard", () => ({ fetchDashboard: vi.fn().mockResolvedValue({}) }));
vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1350 }),
}));
vi.mock("@/api/portfolios", () => ({ fetchPortfolioOverviewLite: vi.fn().mockResolvedValue({}) }));
vi.mock("@/api/invest", () => ({ fetchDCAAnalysis: vi.fn().mockResolvedValue({}) }));

vi.mock("@/stores/authStore", () => ({
  useAuthStore: vi.fn((selector) => {
    const state = {
      login: mockLogin,
      forgotPassword: mockForgotPassword,
      findAccount: mockFindAccount,
    };
    return typeof selector === "function" ? selector(state) : state;
  }),
}));

function renderWithRouter(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLogin.mockResolvedValue(undefined);
  });

  it("이메일·비밀번호 입력 필드와 로그인 버튼을 렌더링한다", () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByLabelText("이메일")).toBeInTheDocument();
    expect(screen.getByLabelText("비밀번호")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "로그인" })).toBeInTheDocument();
  });

  it("Growlio 로고 텍스트를 표시한다", () => {
    renderWithRouter(<LoginPage />);
    expect(screen.getByText("Growlio")).toBeInTheDocument();
  });

  it("로그인 성공 시 /dashboard로 이동한다", async () => {
    renderWithRouter(<LoginPage />);
    fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "password123" } });
    fireEvent.submit(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith("/dashboard"));
  });

  it("로그인 실패 시 에러 메시지를 표시한다", async () => {
    mockLogin.mockRejectedValue(new Error("Invalid credentials"));
    renderWithRouter(<LoginPage />);
    fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "wrong" } });
    fireEvent.submit(screen.getByRole("button", { name: "로그인" }));
    await waitFor(() =>
      expect(screen.getByText("이메일 또는 비밀번호가 올바르지 않습니다")).toBeInTheDocument(),
    );
  });

  it("로그인 중에는 버튼이 비활성화된다", async () => {
    let resolve: () => void;
    mockLogin.mockReturnValue(
      new Promise<void>((r) => {
        resolve = r;
      }),
    );
    renderWithRouter(<LoginPage />);
    fireEvent.change(screen.getByLabelText("이메일"), { target: { value: "test@example.com" } });
    fireEvent.change(screen.getByLabelText("비밀번호"), { target: { value: "pw" } });
    fireEvent.submit(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByText("로그인 중...")).toBeInTheDocument());
    resolve!();
  });
});

describe("ForgotPasswordPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockForgotPassword.mockResolvedValue(undefined);
  });

  it("비밀번호 찾기 제목을 표시한다", () => {
    renderWithRouter(<ForgotPasswordPage />);
    expect(screen.getByText("비밀번호 찾기")).toBeInTheDocument();
  });

  it("이메일 입력 필드를 렌더링한다", () => {
    renderWithRouter(<ForgotPasswordPage />);
    expect(screen.getByPlaceholderText("you@example.com")).toBeInTheDocument();
  });

  it("폼 제출 성공 시 성공 메시지를 표시한다", async () => {
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "user@example.com" },
    });
    fireEvent.submit(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByText(/이메일을 확인해주세요/)).toBeInTheDocument());
  });

  it("폼 제출 실패 시 에러 메시지를 표시한다", async () => {
    mockForgotPassword.mockRejectedValue(new Error("not found"));
    renderWithRouter(<ForgotPasswordPage />);
    fireEvent.change(screen.getByPlaceholderText("you@example.com"), {
      target: { value: "unknown@example.com" },
    });
    fireEvent.submit(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByText(/오류가 발생했습니다/)).toBeInTheDocument());
  });
});

describe("FindAccountPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFindAccount.mockResolvedValue("test@example.com으로 가입된 계정이 있습니다.");
  });

  it("계정 찾기 제목을 표시한다", () => {
    renderWithRouter(<FindAccountPage />);
    expect(screen.getByText("아이디 찾기")).toBeInTheDocument();
  });

  it("이름 입력 필드를 렌더링한다", () => {
    renderWithRouter(<FindAccountPage />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("계정 찾기 성공 시 메시지를 표시한다", async () => {
    renderWithRouter(<FindAccountPage />);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "홍길동" } });
    fireEvent.submit(screen.getByRole("button", { name: /이메일 확인/ }));
    await waitFor(() => expect(screen.getByText(/가입된 계정이 있습니다/)).toBeInTheDocument());
  });
});
