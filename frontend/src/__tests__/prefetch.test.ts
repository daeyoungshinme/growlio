import { describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { prefetchDashboardData } from "@/api/prefetch";
import { QUERY_KEYS } from "@/constants/queryKeys";

vi.mock("@/api/dashboard", () => ({ fetchDashboard: vi.fn().mockResolvedValue({}) }));
vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1300 }),
}));
vi.mock("@/api/portfolios", () => ({
  fetchPortfolios: vi.fn().mockResolvedValue([]),
  fetchPortfolioOverviewLite: vi.fn().mockResolvedValue({}),
}));
vi.mock("@/api/invest", () => ({ fetchDCAAnalysis: vi.fn().mockResolvedValue({}) }));
vi.mock("@/api/settings", () => ({ fetchSettings: vi.fn().mockResolvedValue({}) }));

describe("prefetchDashboardData", () => {
  it("앱 부팅과 로그인이 같은 대시보드 쿼리 목록을 미리 가져온다(settings 포함)", () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "prefetchQuery");

    prefetchDashboardData(qc);

    const keys = spy.mock.calls.map(([opts]) => opts.queryKey);
    expect(keys).toEqual([
      QUERY_KEYS.dashboard,
      QUERY_KEYS.accounts,
      QUERY_KEYS.portfolioOverviewLite,
      QUERY_KEYS.dcaAnalysis,
      QUERY_KEYS.exchangeRate,
      QUERY_KEYS.settings,
    ]);
  });
});
