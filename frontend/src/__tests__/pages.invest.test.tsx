import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// mocks
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

vi.mock("@/api/settings", () => ({
  fetchSettings: vi.fn(),
}));

vi.mock("@/api/invest", () => ({
  fetchDCAAnalysis: vi.fn(),
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateDcaData: vi.fn().mockResolvedValue(undefined),
  invalidateDividendPlanData: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

// Heavy subcomponents
vi.mock("../components/invest/DCAProjectionChart", () => ({
  default: () => <div data-testid="dca-chart">DCAProjectionChart</div>,
}));
vi.mock("@/components/invest/GoalTimelineCard", () => ({
  default: () => <div data-testid="goal-timeline">GoalTimelineCard</div>,
}));
vi.mock("@/components/invest/MonthlyAchievementTable", () => ({
  default: () => <div data-testid="monthly-table">MonthlyAchievementTable</div>,
}));
vi.mock("@/components/invest/YearlyAchievementTable", () => ({
  default: () => <div data-testid="yearly-table">YearlyAchievementTable</div>,
}));
vi.mock("@/components/ErrorBoundary", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/common/SkeletonCard", () => ({
  default: () => <div data-testid="skeleton-card" />,
}));
vi.mock("@/components/common/FormInput", () => ({
  default: ({
    label,
    value,
    onChange,
    placeholder,
    preview,
  }: {
    label: string;
    value: string;
    onChange: React.ChangeEventHandler<HTMLInputElement>;
    placeholder?: string;
    preview?: string;
  }) => (
    <div>
      <label htmlFor={label}>{label}</label>
      <input id={label} value={value} onChange={onChange} placeholder={placeholder} />
      {preview && <p>{preview}</p>}
    </div>
  ),
}));
vi.mock("@/components/common/ConfirmModal", () => ({
  default: ({
    onConfirm,
    onCancel,
    message,
  }: {
    onConfirm: () => void;
    onCancel: () => void;
    message: string;
  }) => (
    <div data-testid="confirm-modal">
      <p>{message}</p>
      <button onClick={onConfirm}>닫기</button>
      <button onClick={onCancel}>계속 편집</button>
    </div>
  ),
}));

import InvestPlanPage from "@/pages/InvestPlanPage";
import { api } from "@/api/client";
import { fetchSettings } from "@/api/settings";
import { fetchDCAAnalysis } from "@/api/invest";
import { toast } from "@/utils/toast";

const mockConfiguredData = {
  is_configured: true,
  settings: {
    monthly_deposit_amount: 500000,
    goal_annual_return_pct: 8,
    goal_amount: 500000000,
    goal_start_date: "2024-01-01",
    goal_initial_amount: 100000000,
  },
  projection_months: [],
  goal_timeline: null,
  yearly_achievements: [],
};

const mockUnconfiguredData = {
  is_configured: false,
  settings: {
    monthly_deposit_amount: null,
    goal_annual_return_pct: null,
    goal_amount: null,
    goal_start_date: null,
    goal_initial_amount: null,
  },
  projection_months: [],
  goal_timeline: null,
  yearly_achievements: [],
};

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <InvestPlanPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InvestPlanPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({
      data: { annual_deposit_goal: null, retirement_target_year: null },
    });
    vi.mocked(fetchSettings).mockResolvedValue({
      annual_deposit_goal: null,
      retirement_target_year: null,
    } as never);
  });

  it("shows loading state", async () => {
    vi.mocked(fetchDCAAnalysis).mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="skeleton-card"]').length).toBeGreaterThan(0);
    });
  });

  it("shows error state with retry button when fetch fails and data is null", async () => {
    vi.mocked(fetchDCAAnalysis).mockRejectedValue(new Error("failed"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("데이터를 불러오지 못했습니다.")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });

  it("renders main page when data is configured", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정")).toBeInTheDocument();
    });
    expect(screen.getByTestId("dca-chart")).toBeInTheDocument();
    expect(screen.getByTestId("goal-timeline")).toBeInTheDocument();
  });

  it("shows 미설정 for unconfigured fields", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockUnconfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정")).toBeInTheDocument();
    });
    const notSet = screen.getAllByText("미설정");
    expect(notSet.length).toBeGreaterThan(0);
  });

  it("shows warning banner when not configured", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockUnconfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/월 적립액, 목표 수익률/)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "지금 설정하기" })).toBeInTheDocument();
  });

  it("does NOT show warning banner when configured", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정")).toBeInTheDocument();
    });
    expect(screen.queryByText(/월 적립액, 목표 수익률/)).not.toBeInTheDocument();
  });

  it("shows configured field values in the settings card", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("2024-01-01")).toBeInTheDocument();
    });
    expect(screen.getByText("8%")).toBeInTheDocument();
  });

  it("shows 스냅샷 자동 when goal_initial_amount is null", async () => {
    const data = {
      ...mockConfiguredData,
      settings: { ...mockConfiguredData.settings, goal_initial_amount: null },
    };
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(data as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("스냅샷 자동")).toBeInTheDocument();
    });
  });

  it("opens edit modal when '설정 편집' button is clicked", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
  });

  it("shows live comma/unit preview under amount fields as the user types", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
    fireEvent.change(screen.getByLabelText("목표 금액 (원)"), {
      target: { value: "500000000" },
    });
    expect(screen.getByText("500,000,000원 (5.00억원)")).toBeInTheDocument();
  });

  it("saves settings successfully", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
    // Click save
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("설정이 저장되었습니다", "success");
    });
  });

  it("shows error toast when save fails", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    vi.mocked(api.put).mockRejectedValue(new Error("save failed"));
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("저장에 실패했습니다", "error");
    });
  });

  it("closes modal immediately when form is not dirty", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
    // Close without changes
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    await waitFor(() => {
      expect(screen.queryByText("적립 계획 설정 편집")).not.toBeInTheDocument();
    });
  });

  it("shows confirm modal when form is dirty and close is attempted", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
    // Modify a field to make form dirty
    const inputs = screen.getAllByRole("textbox");
    if (inputs.length > 0) {
      fireEvent.change(inputs[0], { target: { value: "999999" } });
    }
    // Click cancel
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-modal")).toBeInTheDocument();
    });
  });

  it("confirm modal '닫기' closes the editing modal", async () => {
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(mockConfiguredData as never);
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /설정 편집/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /설정 편집/ }));
    await waitFor(() => {
      expect(screen.getByText("적립 계획 설정 편집")).toBeInTheDocument();
    });
    const inputs = screen.getAllByRole("textbox");
    if (inputs.length > 0) {
      fireEvent.change(inputs[0], { target: { value: "888888" } });
    }
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    await waitFor(() => {
      expect(screen.getByTestId("confirm-modal")).toBeInTheDocument();
    });
    // Confirm closing
    const confirmModal = screen.getByTestId("confirm-modal");
    fireEvent.click(within(confirmModal).getByRole("button", { name: "닫기" }));
    await waitFor(() => {
      expect(screen.queryByText("적립 계획 설정 편집")).not.toBeInTheDocument();
    });
  });
});
