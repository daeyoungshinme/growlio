import { describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/react-query";
import { isHomeEntryPath, prefetchDashboardData } from "@/api/prefetch";
import { QUERY_KEYS } from "@/constants/queryKeys";

vi.mock("@/api/dashboard", () => ({
  fetchDashboard: vi.fn().mockResolvedValue({}),
  fetchActionItems: vi.fn().mockResolvedValue([]),
}));
vi.mock("@/api/challenges", () => ({ fetchChallenges: vi.fn().mockResolvedValue([]) }));
vi.mock("@/api/assets", () => ({
  fetchAccounts: vi.fn().mockResolvedValue([]),
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1300 }),
}));
vi.mock("@/api/portfolios", () => ({ fetchPortfolios: vi.fn().mockResolvedValue([]) }));
vi.mock("@/api/settings", () => ({ fetchSettings: vi.fn().mockResolvedValue({}) }));

describe("prefetchDashboardData", () => {
  it("앱 부팅과 로그인이 같은 홈 쿼리 목록을 미리 가져온다(지금 할 일·챌린지 포함, plans/125 C3)", () => {
    const qc = new QueryClient();
    const spy = vi.spyOn(qc, "prefetchQuery");

    prefetchDashboardData(qc);

    const keys = spy.mock.calls.map(([opts]) => opts.queryKey);
    // 주식 평가손익·목표 달성 예상월은 대시보드 응답에 실려 lite overview·적립 분석은 받지 않는다(plans/151 B1)
    expect(keys).toEqual([
      QUERY_KEYS.dashboard,
      QUERY_KEYS.accounts,
      QUERY_KEYS.exchangeRate,
      QUERY_KEYS.actionItems,
      QUERY_KEYS.challenges,
    ]);
  });
});

describe("isHomeEntryPath (plans/151 B3)", () => {
  it("홈·루트·모르는 경로(홈으로 이동)는 홈 진입", () => {
    for (const path of ["/", "/dashboard", "/unknown"]) expect(isHomeEntryPath(path)).toBe(true);
  });

  it("딥링크로 다른 화면에 들어오면 홈 데이터를 미리 받지 않는다", () => {
    for (const path of [
      "/rebalancing",
      "/invest-plan",
      "/assets",
      "/settings/notifications",
      "/login",
      "/auth/callback",
    ])
      expect(isHomeEntryPath(path)).toBe(false);
  });
});
