import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useDashboardData } from "@/hooks/useDashboardData";
import { ExchangeRateProvider } from "@/context/ExchangeRateContext";

vi.mock("../api/dashboard", () => ({
  fetchDashboard: vi.fn(),
}));

vi.mock("../api/portfolios", () => ({
  fetchPortfolioOverview: vi.fn(),
  fetchPortfolioOverviewLite: vi.fn(),
}));

vi.mock("../api/invest", () => ({
  fetchDCAAnalysis: vi.fn(),
}));

vi.mock("../api/assets", () => ({
  fetchAccounts: vi.fn(),
  fetchExchangeRate: vi.fn(),
}));

const mockDashboardData = {
  total_asset_krw: 100000000,
  total_invested_krw: 80000000,
  total_pnl_krw: 20000000,
  annual_deposit_goal: 24000000,
  ytd_deposit_amount: 12000000,
  estimated_annual_dividends: 2000000,
  annual_dividends_received: 1000000,
};

const mockOverview = {
  total_invested_krw: 80000000,
  total_value_krw: 100000000,
  total_pnl_krw: 20000000,
  stock_allocation: [],
};

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <ExchangeRateProvider>{children}</ExchangeRateProvider>
    </QueryClientProvider>
  );
}

describe("useDashboardData", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { fetchDashboard } = await import("../api/dashboard");
    const { fetchPortfolioOverview, fetchPortfolioOverviewLite } = await import("../api/portfolios");
    const { fetchDCAAnalysis } = await import("../api/invest");
    const { fetchAccounts, fetchExchangeRate } = await import("../api/assets");
    vi.mocked(fetchDashboard).mockResolvedValue(mockDashboardData as never);
    vi.mocked(fetchPortfolioOverview).mockResolvedValue(mockOverview as never);
    vi.mocked(fetchPortfolioOverviewLite).mockResolvedValue(mockOverview as never);
    vi.mocked(fetchDCAAnalysis).mockResolvedValue(null as never);
    vi.mocked(fetchAccounts).mockResolvedValue([]);
    vi.mocked(fetchExchangeRate).mockResolvedValue({ usd_krw: 1350 });
  });

  it("초기 로딩 상태에서 isLoading이 true다", () => {
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    expect(result.current.isLoading).toBe(true);
  });

  it("데이터 로드 완료 후 dashboard 데이터를 반환한다", async () => {
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.data).toEqual(mockDashboardData);
  });

  it("데이터 로드 완료 후 exchangeRate를 반환한다", async () => {
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.exchangeRate).toBe(1350));
  });

  it("API 오류 시 error 상태가 설정된다", async () => {
    const { fetchDashboard } = await import("../api/dashboard");
    vi.mocked(fetchDashboard).mockRejectedValueOnce(new Error("API 오류"));

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.data).toBeUndefined();
  });

  it("accounts가 기본적으로 빈 배열이다", async () => {
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.accountsLoading).toBe(false));
    expect(result.current.accounts).toEqual([]);
  });
});
