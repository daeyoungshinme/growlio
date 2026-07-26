import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── mocks ──
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

vi.mock("@/api/alerts", () => ({
  fetchAlertHistory: vi.fn().mockResolvedValue([]),
  fetchRebalancingAlerts: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

// Heavy sub-sections
vi.mock("@/components/settings/ExchangeRateAlertSection", () => ({
  ExchangeRateAlertSection: () => (
    <div data-testid="exchange-rate-alert-section">ExchangeRateAlertSection</div>
  ),
}));
vi.mock("@/components/settings/StockPriceAlertSection", () => ({
  StockPriceAlertSection: () => (
    <div data-testid="stock-price-alert-section">StockPriceAlertSection</div>
  ),
}));
vi.mock("@/components/settings/MarketSignalAlertSection", () => ({
  MarketSignalAlertSection: () => (
    <div data-testid="market-signal-alert-section">MarketSignalAlertSection</div>
  ),
}));
vi.mock("@/components/settings/NotificationEmailSection", () => ({
  NotificationEmailSection: ({ userEmail }: { userEmail?: string }) => (
    <div data-testid="notification-email-section">{userEmail ?? "no-email"}</div>
  ),
}));

import NotificationSettingsPage from "@/pages/NotificationSettingsPage";
import { api } from "@/api/client";
import { fetchAlertHistory } from "@/api/alerts";

const mockSettings = {
  has_kis: false,
  has_dart: false,
  goal_amount: null,
  goal_annual_return_pct: null,
  annual_deposit_goal: null,
  monthly_deposit_amount: null,
  retirement_target_year: null,
  user_email: "user@example.com",
  notification_email: null,
  annual_dividend_goal: null,
  fcm_token_stored: false,
  composite_signal_alerts_enabled: false,
  goal_achievement_alerts_enabled: true,
  monthly_report_enabled: true,
  recommendation_drift_alert_enabled: true,
  goal_candidate_tickers: [],
  goal_risk_tolerance: "BALANCED",
  goal_max_weight_pct: 30,
  goal_cagr_lookback_years: 5,
  goal_short_term_equity_floor_pct: 20,
};

function renderNotificationSettings() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <NotificationSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // useCollapsible이 localStorage로 접힘 상태를 영속화하므로, 알림 그룹 카드를 여닫는 테스트 간
    // 상태가 새지 않도록 매 테스트 시작 시 초기화한다.
    localStorage.clear();
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/settings") return Promise.resolve({ data: mockSettings });
      return Promise.resolve({ data: {} });
    });
    vi.mocked(fetchAlertHistory).mockResolvedValue([]);
  });

  it("설정으로 돌아가는 링크와 기본 섹션들을 렌더링한다", async () => {
    renderNotificationSettings();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "알림 설정", level: 1 })).toBeInTheDocument();
    });
    expect(screen.getByText("설정").closest("a")).toHaveAttribute("href", "/settings");
    expect(screen.getByTestId("exchange-rate-alert-section")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "주가 알림" }));
    await waitFor(() => {
      expect(screen.getByTestId("stock-price-alert-section")).toBeInTheDocument();
    });
  });

  it("목표 달성 알림 토글을 클릭하면 설정을 저장한다", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    renderNotificationSettings();
    await waitFor(() => {
      expect(screen.getByText("즉시 알림")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /즉시 알림/ }));
    await waitFor(() => {
      expect(screen.getByText("목표 달성 알림")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "목표 달성 알림" }));
    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith("/settings/goal-achievement-alerts", { enabled: false });
    });
  });

  it("월간 리포트 토글을 클릭하면 설정을 저장한다", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    renderNotificationSettings();
    await waitFor(() => {
      expect(screen.getByText("정기 리포트·요약")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /정기 리포트·요약/ }));
    await waitFor(() => {
      expect(screen.getByText("월간 리포트")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "월간 리포트" }));
    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith("/settings/monthly-report-alerts", { enabled: false });
    });
  });

  it("추천 비중 변화 알림 토글을 클릭하면 설정을 저장한다", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    renderNotificationSettings();
    fireEvent.click(screen.getByRole("button", { name: /정기 리포트·요약/ }));
    // mockSettings 로드 전 기본값(false)에서 클릭하는 경합을 피하기 위해 로드 완료(checked) 대기
    await waitFor(() => {
      expect(screen.getByRole("checkbox", { name: "추천 비중 변화 알림" })).toBeChecked();
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "추천 비중 변화 알림" }));
    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith("/settings/recommendation-drift-alert", {
        enabled: false,
      });
    });
  });

  it("시장 모니터링 카드를 펼치면 MarketSignalAlertSection을 표시한다", async () => {
    renderNotificationSettings();
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "알림 설정", level: 1 })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /시장 모니터링/ }));
    await waitFor(() => {
      expect(screen.getByTestId("market-signal-alert-section")).toBeInTheDocument();
    });
  });

  it("?atab=시장 신호 알림 쿼리로 진입하면 시장 모니터링 카드가 자동으로 펼쳐진다", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/settings/notifications?atab=시장 신호 알림"]}>
          <NotificationSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId("market-signal-alert-section")).toBeInTheDocument();
    });
  });

  it("알림 이력이 없을 때 '발송된 알림 이력이 없습니다' 텍스트를 표시한다", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([]);
    renderNotificationSettings();
    fireEvent.click(screen.getByRole("button", { name: "발송 이력" }));
    await waitFor(() => {
      expect(screen.getByText("발송된 알림 이력이 없습니다.")).toBeInTheDocument();
    });
  });

  it("알림 이력이 있을 때 목록을 표시한다", async () => {
    const historyItems = [
      {
        id: "h-1",
        alert_type: "EXCHANGE_RATE",
        message: "환율이 1300원 이하로 떨어졌습니다",
        created_at: "2024-06-01T10:00:00Z",
      },
      {
        id: "h-2",
        alert_type: "REBALANCING",
        message: "리밸런싱 알림",
        created_at: "2024-06-02T10:00:00Z",
      },
    ];
    vi.mocked(fetchAlertHistory).mockResolvedValue(historyItems as never);
    renderNotificationSettings();
    fireEvent.click(screen.getByRole("button", { name: "발송 이력" }));
    await waitFor(() => {
      expect(screen.getByText("환율이 1300원 이하로 떨어졌습니다")).toBeInTheDocument();
    });
    expect(screen.getAllByText("환율 알림").length).toBeGreaterThan(0);
    expect(screen.getAllByText("리밸런싱 알림").length).toBeGreaterThan(0);
  });

  it("알림 타입 레이블 매핑에 없는 알림 타입이면 원래 타입을 표시한다", async () => {
    const historyItems = [
      {
        id: "h-1",
        alert_type: "UNKNOWN_TYPE",
        message: "알 수 없는 알림",
        created_at: "2024-06-01T10:00:00Z",
      },
    ];
    vi.mocked(fetchAlertHistory).mockResolvedValue(historyItems as never);
    renderNotificationSettings();
    fireEvent.click(screen.getByRole("button", { name: "발송 이력" }));
    await waitFor(() => {
      expect(screen.getByText("UNKNOWN_TYPE")).toBeInTheDocument();
    });
  });

  it("STOCK_PRICE 알림 타입 레이블을 올바르게 표시한다", async () => {
    const historyItems = [
      {
        id: "h-1",
        alert_type: "STOCK_PRICE",
        message: "주가 알림 메시지",
        created_at: "2024-06-01T10:00:00Z",
      },
    ];
    vi.mocked(fetchAlertHistory).mockResolvedValue(historyItems as never);
    renderNotificationSettings();
    await waitFor(() => {
      expect(screen.getByText("주가 알림")).toBeInTheDocument();
    });
  });

  it("NotificationEmailSection에 user_email을 전달한다", async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { ...mockSettings, user_email: "test@test.com" },
    });
    renderNotificationSettings();
    await waitFor(() => {
      expect(screen.getByTestId("notification-email-section")).toHaveTextContent("test@test.com");
    });
  });
});
