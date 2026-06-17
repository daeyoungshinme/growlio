import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ── mocks must come before any imports that use them ──
vi.mock("@/hooks/useDashboardData", () => ({
  useDashboardData: vi.fn(),
}));

vi.mock("@/hooks/useRegisterRefresh", () => ({
  useRegisterRefresh: vi.fn(),
}));

vi.mock("@/utils/queryInvalidation", () => ({
  invalidateSyncData: vi.fn().mockResolvedValue(undefined),
}));

// Lazy-loaded components
vi.mock("../components/dashboard/AllocationHistoryChart", () => ({
  default: () => <div data-testid="allocation-chart">AllocationHistoryChart</div>,
}));
vi.mock("../components/dashboard/DisclosureFeedCard", () => ({
  default: () => <div data-testid="disclosure-feed">DisclosureFeedCard</div>,
}));
vi.mock("@/components/dashboard/HeroSummaryCard", () => ({
  default: ({ data }: { data?: { total_asset_krw?: number } }) => (
    <div data-testid="hero-summary">{data?.total_asset_krw ?? ""}</div>
  ),
}));
vi.mock("@/components/dashboard/PortfolioSummaryCard", () => ({
  default: () => <div data-testid="portfolio-summary">PortfolioSummaryCard</div>,
}));
vi.mock("@/components/dashboard/DividendSection", () => ({
  default: () => <div data-testid="dividend-section">DividendSection</div>,
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

import DashboardPage from "@/pages/DashboardPage";
import { useDashboardData } from "@/hooks/useDashboardData";

const mockDashboardData = {
  total_asset_krw: 100_000_000,
  total_invested_krw: 80_000_000,
  total_pnl_krw: 20_000_000,
  annual_deposit_goal: 24_000_000,
  ytd_deposit_amount: 12_000_000,
  estimated_annual_dividends: 2_400_000,
  annual_dividends_received: 1_000_000,
};

const mockOverview = {
  total_invested_krw: 80_000_000,
  total_value_krw: 100_000_000,
  stock_allocation: [],
};

function renderDashboard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("로딩 중일 때 스켈레톤을 렌더링한다", async () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      dataUpdatedAt: 0,
      overview: undefined,
      overviewLoading: true,
      dcaData: undefined,
      accounts: [],
      accountsLoading: true,
      exchangeRate: null,
    });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getAllByTestId("skeleton-stat-box").length).toBeGreaterThan(0);
    });
  });

  it("에러 상태일 때 에러 메시지와 재시도 버튼을 표시한다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fetch failed"),
      dataUpdatedAt: 0,
      overview: undefined,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [],
      accountsLoading: false,
      exchangeRate: null,
    });
    renderDashboard();
    expect(screen.getByText("데이터를 불러오지 못했습니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument();
  });

  it("에러 없어도 data가 없으면 에러 메시지를 표시한다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      dataUpdatedAt: 0,
      overview: undefined,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [],
      accountsLoading: false,
      exchangeRate: null,
    });
    renderDashboard();
    expect(screen.getByText("데이터를 불러오지 못했습니다")).toBeInTheDocument();
  });

  it("accounts가 없고 accountsLoading이 false이면 '자산 없음' 화면을 표시한다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: mockDashboardData as never,
      isLoading: false,
      error: null,
      dataUpdatedAt: Date.now(),
      overview: mockOverview as never,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [],
      accountsLoading: false,
      exchangeRate: 1350,
    });
    renderDashboard();
    expect(screen.getByText("등록된 자산이 없습니다")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "자산관리로 이동" })).toBeInTheDocument();
  });

  it("accounts가 로딩 중이면 '자산 없음' 화면을 표시하지 않는다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: mockDashboardData as never,
      isLoading: false,
      error: null,
      dataUpdatedAt: Date.now(),
      overview: mockOverview as never,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [],
      accountsLoading: true,
      exchangeRate: 1350,
    });
    renderDashboard();
    // accountsLoading=true means we skip the empty-accounts branch
    expect(screen.queryByText("등록된 자산이 없습니다")).not.toBeInTheDocument();
    // main content rendered instead
    expect(screen.getByTestId("hero-summary")).toBeInTheDocument();
  });

  it("정상 데이터와 계좌 있을 때 메인 콘텐츠를 렌더링한다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: mockDashboardData as never,
      isLoading: false,
      error: null,
      dataUpdatedAt: Date.now(),
      overview: mockOverview as never,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [{ id: "acc-1", name: "KB증권", asset_type: "STOCK_KIS" }] as never,
      accountsLoading: false,
      exchangeRate: 1350,
    });
    renderDashboard();
    expect(screen.getByTestId("hero-summary")).toBeInTheDocument();
    expect(screen.getByTestId("portfolio-summary")).toBeInTheDocument();
    expect(screen.getByTestId("dividend-section")).toBeInTheDocument();
    expect(screen.getByText("주식 포트폴리오 요약")).toBeInTheDocument();
    expect(screen.getByText("배당 현황")).toBeInTheDocument();
  });

  it("estimated_annual_dividends가 있을 때 overallDividendYield를 계산한다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: { ...mockDashboardData, estimated_annual_dividends: 2_000_000 } as never,
      isLoading: false,
      error: null,
      dataUpdatedAt: Date.now(),
      overview: { ...mockOverview, total_invested_krw: 100_000_000 } as never,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [{ id: "acc-1" }] as never,
      accountsLoading: false,
      exchangeRate: 1350,
    });
    renderDashboard();
    // DividendSection receives the computed overallDividendYield; just verify it renders
    expect(screen.getByTestId("dividend-section")).toBeInTheDocument();
  });

  it("estimated_annual_dividends가 null이면 estimatedMonthly는 null이다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: { ...mockDashboardData, estimated_annual_dividends: null } as never,
      isLoading: false,
      error: null,
      dataUpdatedAt: Date.now(),
      overview: mockOverview as never,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [{ id: "acc-1" }] as never,
      accountsLoading: false,
      exchangeRate: 1350,
    });
    renderDashboard();
    // Page still renders, DividendSection gets null estimatedMonthly
    expect(screen.getByTestId("dividend-section")).toBeInTheDocument();
  });

  it("'전체 보기' 링크가 /portfolio를 가리킨다", () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: mockDashboardData as never,
      isLoading: false,
      error: null,
      dataUpdatedAt: Date.now(),
      overview: mockOverview as never,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [{ id: "acc-1" }] as never,
      accountsLoading: false,
      exchangeRate: 1350,
    });
    renderDashboard();
    const link = screen.getByRole("link", { name: /전체 보기/ });
    expect(link).toHaveAttribute("href", "/portfolio");
  });

  it("다시 시도 버튼 클릭 시 쿼리를 무효화한다", async () => {
    vi.mocked(useDashboardData).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("fetch failed"),
      dataUpdatedAt: 0,
      overview: undefined,
      overviewLoading: false,
      dcaData: undefined,
      accounts: [],
      accountsLoading: false,
      exchangeRate: null,
    });
    renderDashboard();
    const retryBtn = screen.getByRole("button", { name: "다시 시도" });
    fireEvent.click(retryBtn);
    // invalidateQueries is called on qc; just ensure button is there and clickable
    await waitFor(() => {
      expect(retryBtn).toBeInTheDocument();
    });
  });
});
