import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: (sel: (s: { isDark: boolean; toggle: () => void }) => unknown) => {
    const s = { isDark: false, toggle: vi.fn() };
    return typeof sel === "function" ? sel(s) : s;
  },
}));

vi.mock("@/hooks/useEconomicIndicators", () => ({
  useEconomicIndicators: vi.fn(),
  useIndicatorCalendar: vi.fn(),
  useIndicatorHistory: vi.fn(),
  useSubscribeMutation: vi.fn(),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

vi.mock("@/components/market/IndicatorCard", () => ({
  default: ({
    indicator,
    isSelected,
    onSelect,
    onToggleSubscribe,
    subscribed,
  }: {
    indicator: { code: string; name: string };
    isSelected: boolean;
    onSelect: () => void;
    onToggleSubscribe: () => void;
    subscribed: boolean;
  }) => (
    <div data-testid={`indicator-card-${indicator.code}`} data-selected={isSelected}>
      <span>{indicator.name}</span>
      <button onClick={onSelect}>select</button>
      <button onClick={onToggleSubscribe}>
        {subscribed ? "unsubscribe" : "subscribe"}
      </button>
    </div>
  ),
}));

vi.mock("@/components/market/EconomicCalendar", () => ({
  default: ({ events }: { events: unknown[] }) => (
    <div data-testid="economic-calendar">{events.length} events</div>
  ),
}));

vi.mock("@/components/market/IndicatorHistoryChart", () => ({
  default: ({ name }: { name: string }) => (
    <div data-testid="history-chart">{name}</div>
  ),
}));

vi.mock("@/components/common/SkeletonCard", () => ({
  default: () => <div data-testid="skeleton-card" />,
}));

import MarketPage from "@/pages/MarketPage";
import {
  useEconomicIndicators,
  useIndicatorCalendar,
  useIndicatorHistory,
  useSubscribeMutation,
} from "@/hooks/useEconomicIndicators";
import { toast } from "@/utils/toast";

const mockIndicators = [
  {
    code: "UNRATE",
    name: "실업률",
    description: "미국 실업률",
    unit: "%",
    value: 3.9,
    subscribed: false,
    change: 0.1,
    frequency: "monthly",
    last_updated: "2024-06-01",
  },
  {
    code: "FEDFUNDS",
    name: "기준금리",
    description: "연준 기준금리",
    unit: "%",
    value: 5.5,
    subscribed: true,
    change: 0,
    frequency: "monthly",
    last_updated: "2024-06-01",
  },
];

const mockSubscribeFn = vi.fn().mockResolvedValue({});
const mockUnsubscribeFn = vi.fn().mockResolvedValue({});

function setupMocks(overrides: Partial<{
  isLoading: boolean;
  isError: boolean;
  indicators: typeof mockIndicators;
  calendarLoading: boolean;
  historyLoading: boolean;
}> = {}) {
  const {
    isLoading = false,
    isError = false,
    indicators = mockIndicators,
    calendarLoading = false,
    historyLoading = false,
  } = overrides;

  vi.mocked(useEconomicIndicators).mockReturnValue({
    data: isLoading || isError ? undefined : indicators,
    isLoading,
    isError,
    refetch: vi.fn(),
    isFetching: false,
  } as never);

  vi.mocked(useIndicatorCalendar).mockReturnValue({
    data: [{ id: "1", name: "CPI", date: "2024-07-01" }],
    isLoading: calendarLoading,
  } as never);

  vi.mocked(useIndicatorHistory).mockReturnValue({
    data: [{ date: "2024-01", value: 3.9 }],
    isLoading: historyLoading,
  } as never);

  vi.mocked(useSubscribeMutation).mockReturnValue({
    subscribe: {
      mutateAsync: mockSubscribeFn,
      isPending: false,
    },
    unsubscribe: {
      mutateAsync: mockUnsubscribeFn,
      isPending: false,
    },
  } as never);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MarketPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("MarketPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSubscribeFn.mockResolvedValue({});
    mockUnsubscribeFn.mockResolvedValue({});
  });

  it("shows loading skeleton for indicators when loading", () => {
    setupMocks({ isLoading: true });
    renderPage();
    expect(screen.getAllByTestId("skeleton-card").length).toBeGreaterThan(0);
  });

  it("shows calendar loading state", () => {
    setupMocks({ calendarLoading: true });
    renderPage();
    // Loading state shows pulsing divs (not economic-calendar testid)
    expect(screen.queryByTestId("economic-calendar")).not.toBeInTheDocument();
  });

  it("shows error message when indicators fail to load", () => {
    setupMocks({ isError: true });
    renderPage();
    expect(
      screen.getByText(/지표 데이터를 불러오는 중 오류가 발생했습니다/)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });

  it("renders indicator cards when data is loaded", () => {
    setupMocks();
    renderPage();
    expect(screen.getByTestId("indicator-card-UNRATE")).toBeInTheDocument();
    expect(screen.getByTestId("indicator-card-FEDFUNDS")).toBeInTheDocument();
    expect(screen.getByText("실업률")).toBeInTheDocument();
    expect(screen.getByText("기준금리")).toBeInTheDocument();
  });

  it("renders economic calendar", () => {
    setupMocks();
    renderPage();
    expect(screen.getByTestId("economic-calendar")).toBeInTheDocument();
  });

  it("shows page title", () => {
    setupMocks();
    renderPage();
    expect(screen.getByText("시장 지표")).toBeInTheDocument();
  });

  it("selecting an indicator shows the history chart", async () => {
    setupMocks();
    renderPage();
    // Select the UNRATE indicator
    const selectBtn = screen.getAllByRole("button", { name: "select" })[0];
    fireEvent.click(selectBtn);
    await waitFor(() => {
      expect(screen.getByTestId("history-chart")).toBeInTheDocument();
    });
  });

  it("clicking the same indicator deselects it (toggle off)", async () => {
    setupMocks();
    renderPage();
    const selectBtn = screen.getAllByRole("button", { name: "select" })[0];
    fireEvent.click(selectBtn);
    await waitFor(() => {
      expect(screen.getByTestId("history-chart")).toBeInTheDocument();
    });
    fireEvent.click(selectBtn);
    await waitFor(() => {
      expect(screen.queryByTestId("history-chart")).not.toBeInTheDocument();
    });
  });

  it("shows history chart loading state when selected and loading", async () => {
    setupMocks({ historyLoading: true });
    renderPage();
    const selectBtn = screen.getAllByRole("button", { name: "select" })[0];
    fireEvent.click(selectBtn);
    await waitFor(() => {
      expect(screen.getByText(/차트 로딩 중/)).toBeInTheDocument();
    });
  });

  it("subscribing an unsubscribed indicator shows success toast", async () => {
    setupMocks();
    renderPage();
    // UNRATE has subscribed: false => button label is "subscribe"
    const subscribeBtn = screen.getAllByRole("button", { name: "subscribe" })[0];
    fireEvent.click(subscribeBtn);
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("발표 시 이메일 알림을 받습니다.", "success");
    });
  });

  it("unsubscribing a subscribed indicator shows success toast", async () => {
    setupMocks();
    renderPage();
    // FEDFUNDS has subscribed: true => button label is "unsubscribe"
    const unsubscribeBtn = screen.getByRole("button", { name: "unsubscribe" });
    fireEvent.click(unsubscribeBtn);
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("알림 구독을 해제했습니다.", "success");
    });
  });

  it("shows error toast when subscribe fails", async () => {
    // Error with empty message forces extractErrorMessage to use the fallback string
    mockSubscribeFn.mockRejectedValue(new Error());
    setupMocks();
    renderPage();
    const subscribeBtn = screen.getAllByRole("button", { name: "subscribe" })[0];
    fireEvent.click(subscribeBtn);
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.stringContaining("구독 처리 중 오류"),
        "error"
      );
    });
  });

  it("refresh button is present and clickable", () => {
    setupMocks();
    const refetchMock = vi.fn();
    vi.mocked(useEconomicIndicators).mockReturnValue({
      data: mockIndicators,
      isLoading: false,
      isError: false,
      refetch: refetchMock,
      isFetching: false,
    } as never);
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "새로고침" }));
    expect(refetchMock).toHaveBeenCalled();
  });

  it("refresh button shows spinner when fetching", () => {
    vi.mocked(useEconomicIndicators).mockReturnValue({
      data: mockIndicators,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
      isFetching: true,
    } as never);
    vi.mocked(useIndicatorCalendar).mockReturnValue({
      data: [],
      isLoading: false,
    } as never);
    vi.mocked(useIndicatorHistory).mockReturnValue({
      data: [],
      isLoading: false,
    } as never);
    vi.mocked(useSubscribeMutation).mockReturnValue({
      subscribe: { mutateAsync: mockSubscribeFn, isPending: false },
      unsubscribe: { mutateAsync: mockUnsubscribeFn, isPending: false },
    } as never);
    renderPage();
    const refreshBtn = screen.getByRole("button", { name: "새로고침" });
    expect(refreshBtn).toBeDisabled();
  });
});
