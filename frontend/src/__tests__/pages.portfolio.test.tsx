import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
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

vi.mock("@/api/assets", () => ({
  syncAllAccounts: vi.fn().mockResolvedValue({ total: 2, status: "started" }),
  fetchAccounts: vi.fn().mockResolvedValue([]),
  INVESTMENT_HORIZON_LABELS: { SHORT_TERM: "단기", MID_TERM: "중기", LONG_TERM: "장기" },
}));

vi.mock("@/hooks/useRegisterRefresh", () => ({
  useRegisterRefresh: vi.fn(),
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateSyncData: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

// Lazy loaded subcomponents
vi.mock("../components/portfolio/TreemapChart", () => ({
  default: () => <div data-testid="treemap-chart">TreemapChart</div>,
}));
vi.mock("../components/portfolio/DomesticForeignBar", () => ({
  default: () => <div data-testid="domestic-foreign-bar">DomesticForeignBar</div>,
}));
vi.mock("../components/portfolio-analysis/TaxOptimizationCard", () => ({
  default: () => <div data-testid="tax-optimization">TaxOptimizationCard</div>,
}));
vi.mock("../components/portfolio-analysis/TaxLimitsSection", () => ({
  default: () => <div data-testid="tax-limits-section">TaxLimitsSection</div>,
}));

vi.mock("@/components/assets/StockHoldingsTable", () => ({
  default: () => <div data-testid="stock-holdings-table">StockHoldingsTable</div>,
}));
vi.mock("@/components/portfolio/DividendTab", () => ({
  default: () => <div data-testid="dividend-tab">DividendTab</div>,
}));
vi.mock("@/components/ErrorBoundary", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock("@/components/common/SkeletonCard", () => ({
  default: () => <div data-testid="skeleton-card" />,
}));
vi.mock("@/components/common/SkeletonStatBox", () => ({
  default: () => <div data-testid="skeleton-stat-box" />,
}));

import PortfolioPage from "@/pages/PortfolioPage";
import { api } from "@/api/client";
import { toast } from "@/utils/toast";
import { fetchAccounts, syncAllAccounts } from "@/api/assets";
import { useSyncStore } from "@/stores/syncStore";

const mockPortfolioData = {
  total_stock_krw: 50_000_000,
  total_invested_krw: 40_000_000,
  unrealized_pnl_krw: 10_000_000,
  stock_return_pct: 25,
  accounts: [
    { id: "acc-1", asset_type: "STOCK_KIS", name: "KIS 계좌" },
    { id: "acc-2", asset_type: "STOCK_KIWOOM", name: "키움 계좌" },
  ],
  all_positions: [
    {
      ticker: "005930",
      name: "삼성전자",
      market: "KOSPI",
      value_krw: 3_000_000,
      qty: 1,
      avg_price: 70000,
      current_price: 80000,
    },
    {
      ticker: "AAPL",
      name: "Apple",
      market: "NASDAQ",
      value_krw: 2_000_000,
      qty: 1,
      avg_price: 150000,
      current_price: 160000,
    },
  ],
  stock_allocation: [
    { ticker: "005930", name: "삼성전자", value_krw: 3_000_000, pct: 60 },
    { ticker: "AAPL", name: "Apple", value_krw: 2_000_000, pct: 40 },
  ],
};

function renderPortfolio(search = "") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/portfolio${search}`]}>
        <Routes>
          <Route path="/portfolio" element={<PortfolioPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PortfolioPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSyncStore.getState().reset();
  });

  it("로딩 중일 때 스켈레톤을 렌더링한다", async () => {
    // Make api.get hang forever (pending)
    vi.mocked(api.get).mockReturnValue(new Promise(() => {}));
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getAllByTestId("skeleton-stat-box").length).toBeGreaterThan(0);
    });
  });

  it("에러 시 오류 메시지와 재시도 버튼을 표시한다", async () => {
    vi.mocked(api.get).mockRejectedValue(new Error("network error"));
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("데이터를 불러오지 못했습니다")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });

  it("정상 데이터일 때 포트폴리오 기본 요약 정보를 표시한다 (종목 현황 탭)", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      if (url === "/dividends/summary") return Promise.resolve({ data: {} });
      if (url === "/dividends/by-ticker") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("주식 총평가액")).toBeInTheDocument();
    });
    expect(screen.getByTestId("stock-holdings-table")).toBeInTheDocument();
  });

  it("unrealized_pnl_krw가 양수일 때 + 기호를 표시한다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText(/평가손익/)).toBeInTheDocument();
    });
    // Positive pnl shows + sign
    expect(screen.getByText(/\+/)).toBeInTheDocument();
  });

  it("unrealized_pnl_krw가 음수일 때 - 기호를 표시한다", async () => {
    const negativeData = {
      ...mockPortfolioData,
      unrealized_pnl_krw: -500_000,
      stock_return_pct: -1.25,
    };
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: negativeData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText(/평가손익/)).toBeInTheDocument();
    });
    expect(screen.getByText(/-1.25%\)/)).toBeInTheDocument();
  });

  it("'배당' 탭을 선택하면 DividendTab이 렌더링된다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      if (url === "/dividends/summary") return Promise.resolve({ data: {} });
      if (url === "/dividends/by-ticker") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio("?portfolioTab=배당");
    await waitFor(() => {
      expect(screen.getByTestId("dividend-tab")).toBeInTheDocument();
    });
  });

  it("'세금' 탭을 선택하면 TaxLimitsSection과 TaxOptimizationCard가 함께 렌더링된다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio("?portfolioTab=세금");
    await waitFor(() => {
      expect(screen.getByTestId("tax-limits-section")).toBeInTheDocument();
      expect(screen.getByTestId("tax-optimization")).toBeInTheDocument();
    });
  });

  it("유효하지 않은 탭 파라미터는 '종목 현황' 기본 탭으로 폴백된다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio("?portfolioTab=invalid-tab");
    await waitFor(() => {
      expect(screen.getByTestId("stock-holdings-table")).toBeInTheDocument();
    });
  });

  it("국내/해외 포지션이 있을 때 marketChartData를 계산한다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByTestId("domestic-foreign-bar")).toBeInTheDocument();
    });
  });

  it("포지션이 없으면 빈 marketChartData가 되고 여전히 렌더링된다", async () => {
    const emptyPositions = { ...mockPortfolioData, all_positions: [] };
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: emptyPositions });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("주식 총평가액")).toBeInTheDocument();
    });
  });

  it("계좌 수를 표시한다", async () => {
    vi.mocked(fetchAccounts).mockResolvedValueOnce([
      { id: "acc-1", asset_type: "STOCK_KIS", name: "KIS 계좌" },
      { id: "acc-2", asset_type: "STOCK_KIWOOM", name: "키움 계좌" },
    ] as never);
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("전체 계좌 (2개)")).toBeInTheDocument();
    });
  });

  it("계좌에 투자기간 태그가 있으면 투자기간별 자산현황이 표시된다", async () => {
    const horizonData = {
      ...mockPortfolioData,
      accounts: [
        {
          id: "acc-1",
          asset_type: "STOCK_KIS",
          name: "KIS 계좌",
          amount_krw: 30_000_000,
          investment_horizon: "LONG_TERM",
        },
        {
          id: "acc-2",
          asset_type: "STOCK_KIWOOM",
          name: "키움 계좌",
          amount_krw: 20_000_000,
          investment_horizon: "SHORT_TERM",
        },
      ],
    };
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: horizonData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("투자기간별 자산현황")).toBeInTheDocument();
    });
  });

  it("특정 계좌를 선택하면 투자기간 태그가 있어도 투자기간별 자산현황을 표시하지 않는다", async () => {
    const horizonData = {
      ...mockPortfolioData,
      accounts: [
        {
          id: "acc-1",
          asset_type: "STOCK_KIS",
          name: "KIS 계좌",
          amount_krw: 30_000_000,
          investment_horizon: "LONG_TERM",
        },
      ],
    };
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: horizonData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio("?account=acc-1");
    await waitFor(() => {
      expect(screen.getByText("주식 총평가액")).toBeInTheDocument();
    });
    expect(screen.queryByText("투자기간별 자산현황")).not.toBeInTheDocument();
  });

  it("계좌에 투자기간 태그가 없으면 투자기간별 자산현황을 표시하지 않는다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByText("주식 총평가액")).toBeInTheDocument();
    });
    expect(screen.queryByText("투자기간별 자산현황")).not.toBeInTheDocument();
  });

  it("전체 갱신 버튼을 클릭하면 백그라운드 동기화를 시작하고 진행 상태를 표시한다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    vi.mocked(syncAllAccounts).mockResolvedValue({ total: 2, status: "started" });
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /전체 갱신/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /전체 갱신/ }));
    await waitFor(() => {
      expect(syncAllAccounts).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /0\/2 갱신 중/ })).toBeInTheDocument();
    });
  });

  it("동기화 시작 요청이 실패하면 에러 토스트를 표시한다", async () => {
    vi.mocked(api.get).mockImplementation((url: string) => {
      if (url === "/portfolio/overview") return Promise.resolve({ data: mockPortfolioData });
      if (url === "/dividends/positions") return Promise.resolve({ data: [] });
      return Promise.resolve({ data: {} });
    });
    vi.mocked(syncAllAccounts).mockRejectedValue(new Error("sync failed"));
    renderPortfolio();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /전체 갱신/ })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /전체 갱신/ }));
    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(expect.any(String), "error");
    });
  });
});
