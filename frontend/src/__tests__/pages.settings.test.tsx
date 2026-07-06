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

vi.mock("@/stores/themeStore", () => ({
  useThemeStore: (sel: (s: { isDark: boolean; toggle: () => void }) => unknown) => {
    const s = { isDark: false, toggle: vi.fn() };
    return typeof sel === "function" ? sel(s) : s;
  },
}));

vi.mock("@/hooks/useLogout", () => ({
  useLogout: () => vi.fn(),
}));

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
vi.mock("@/components/settings/DCASettingsSection", () => ({
  DCASettingsSection: () => <div data-testid="dca-settings-section">DCASettingsSection</div>,
}));

import SettingsPage from "@/pages/SettingsPage";
import { api } from "@/api/client";
import { toast } from "@/utils/toast";
import { fetchAlertHistory } from "@/api/alerts";

const mockSettings = {
  has_dart: false,
  user_email: "user@example.com",
};

function renderSettings() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/settings") return Promise.resolve({ data: mockSettings });
      if (url === "/assets") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    vi.mocked(fetchAlertHistory).mockResolvedValue([]);
  });

  it("기본 섹션들을 렌더링한다", async () => {
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("DART OpenAPI (금융감독원)")).toBeInTheDocument();
    });
    expect(screen.getByTestId("exchange-rate-alert-section")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "주가 알림" }));
    await waitFor(() => {
      expect(screen.getByTestId("stock-price-alert-section")).toBeInTheDocument();
    });
  });

  it("시장 신호 알림 탭을 클릭하면 MarketSignalAlertSection을 표시한다", async () => {
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("DART OpenAPI (금융감독원)")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "시장 신호 알림" }));
    await waitFor(() => {
      expect(screen.getByTestId("market-signal-alert-section")).toBeInTheDocument();
    });
  });

  it("알림 이력이 없을 때 '발송된 알림 이력이 없습니다' 텍스트를 표시한다", async () => {
    vi.mocked(fetchAlertHistory).mockResolvedValue([]);
    renderSettings();
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
    renderSettings();
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
    renderSettings();
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
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("주가 알림")).toBeInTheDocument();
    });
  });

  it("has_dart가 true이면 삭제 버튼을 표시한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...mockSettings, has_dart: true } });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "삭제" })).toBeInTheDocument();
    });
  });

  it("has_dart가 false이면 삭제 버튼을 표시하지 않는다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...mockSettings, has_dart: false } });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByText("DART OpenAPI (금융감독원)")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "삭제" })).not.toBeInTheDocument();
  });

  it("DART API 키를 저장하면 성공 토스트를 표시한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockSettings });
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByPlaceholderText("DART OpenAPI 인증키")).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText("DART OpenAPI 인증키"), {
      target: { value: "test-api-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("DART API 키가 저장되었습니다", "success");
    });
  });

  it("DART API 키 저장 실패 시 에러 토스트를 표시한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockSettings });
    vi.mocked(api.put).mockRejectedValue(new Error("server error"));
    renderSettings();
    await waitFor(() => {
      expect(screen.getByPlaceholderText("DART OpenAPI 인증키")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith("저장에 실패했습니다", "error");
    });
  });

  it("has_dart가 true이면 placeholder가 마스킹된다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...mockSettings, has_dart: true } });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
    });
  });

  it("DART 삭제 버튼 클릭 시 DELETE를 호출한다", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { ...mockSettings, has_dart: true } });
    vi.mocked(api.delete).mockResolvedValue({ data: {} });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "삭제" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "삭제" }));
    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith("/settings/dart");
    });
    expect(toast).toHaveBeenCalledWith("DART API 키가 삭제되었습니다", "success");
  });

  it("NotificationEmailSection에 user_email을 전달한다", async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { ...mockSettings, user_email: "test@test.com" },
    });
    renderSettings();
    await waitFor(() => {
      expect(screen.getByTestId("notification-email-section")).toHaveTextContent("test@test.com");
    });
  });
});
