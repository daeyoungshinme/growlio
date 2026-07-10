import { describe, it, expect, vi, beforeEach } from "vitest";

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

import { api } from "@/api/client";
import {
  fetchSettings,
  updateAutoDca,
  registerPushToken,
  updateGoalCandidateTickers,
} from "@/api/settings";
import { fetchDCAAnalysis, fetchDividendPlan } from "@/api/invest";
import { fetchOverseasPositionsTax, fetchTaxSummary } from "@/api/tax";
import {
  fetchBacktestPortfolios,
  createBacktestPortfolio,
  updateBacktestPortfolio,
  deleteBacktestPortfolio,
  runBacktest,
  runCorrelation,
} from "@/api/backtest";
import { fetchMonthlyOptimization } from "@/api/dividends";
import { fetchInsights } from "@/api/insights";
import { fetchPortfolioRisk, fetchRebalancingStrategy } from "@/api/risk";
import { fetchInflationSummary } from "@/api/economicIndicators";

describe("api/settings", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchSettings calls GET /settings", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchSettings();
    expect(api.get).toHaveBeenCalledWith("/settings");
  });

  it("updateAutoDca calls PUT /settings/auto-dca", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    const payload = {
      enabled: true,
      day: 15,
      amount: 100000,
      portfolio_id: null,
      account_id: null,
    };
    await updateAutoDca(payload);
    expect(api.put).toHaveBeenCalledWith("/settings/auto-dca", payload);
  });

  it("registerPushToken calls PUT /settings/push-token", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    await registerPushToken("fcm-token-123");
    expect(api.put).toHaveBeenCalledWith("/settings/push-token", { fcm_token: "fcm-token-123" });
  });

  it("registerPushToken accepts null token", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    await registerPushToken(null);
    expect(api.put).toHaveBeenCalledWith("/settings/push-token", { fcm_token: null });
  });

  it("updateGoalCandidateTickers calls PUT /settings/goal-candidate-tickers", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    const tickers = [{ ticker: "TLT", name: "iShares 20+ Year Treasury Bond ETF", market: "NYSE" }];
    await updateGoalCandidateTickers(tickers);
    expect(api.put).toHaveBeenCalledWith("/settings/goal-candidate-tickers", { tickers });
  });
});

describe("api/invest", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchDCAAnalysis calls GET /invest/dca-analysis", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchDCAAnalysis();
    expect(api.get).toHaveBeenCalledWith("/invest/dca-analysis");
  });

  it("fetchDividendPlan calls GET /invest/dividend-plan", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchDividendPlan();
    expect(api.get).toHaveBeenCalledWith("/invest/dividend-plan");
  });
});

describe("api/tax", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchOverseasPositionsTax calls GET /tax/overseas-positions", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchOverseasPositionsTax();
    expect(api.get).toHaveBeenCalledWith("/tax/overseas-positions");
  });

  it("fetchTaxSummary calls GET /tax/summary without year", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchTaxSummary();
    expect(api.get).toHaveBeenCalledWith("/tax/summary", { params: undefined });
  });

  it("fetchTaxSummary calls GET /tax/summary with year", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchTaxSummary(2024);
    expect(api.get).toHaveBeenCalledWith("/tax/summary", { params: { year: 2024 } });
  });
});

describe("api/backtest", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchBacktestPortfolios calls GET /backtest/portfolios", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchBacktestPortfolios();
    expect(api.get).toHaveBeenCalledWith("/backtest/portfolios");
  });

  it("createBacktestPortfolio calls POST /backtest/portfolios", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    const body = { name: "테스트", holdings: [{ ticker: "005930", market: "KOSPI", weight: 100 }] };
    await createBacktestPortfolio(body);
    expect(api.post).toHaveBeenCalledWith("/backtest/portfolios", body);
  });

  it("updateBacktestPortfolio calls PUT /backtest/portfolios/:id", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: {} });
    await updateBacktestPortfolio("port-1", { name: "업데이트" });
    expect(api.put).toHaveBeenCalledWith("/backtest/portfolios/port-1", { name: "업데이트" });
  });

  it("deleteBacktestPortfolio calls DELETE /backtest/portfolios/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({});
    await deleteBacktestPortfolio("port-1");
    expect(api.delete).toHaveBeenCalledWith("/backtest/portfolios/port-1");
  });

  it("runBacktest calls POST /backtest/run", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    const req = {
      portfolio_ids: ["port-1"],
      start_date: "2020-01-01",
      end_date: "2023-12-31",
      include_spy: true,
      include_real_portfolio: false,
      reinvest_dividends: true,
    };
    await runBacktest(req);
    expect(api.post).toHaveBeenCalledWith("/backtest/run", req);
  });

  it("runCorrelation calls POST /backtest/correlation", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: {} });
    const req = { portfolio_ids: ["port-1"], start_date: "2020-01-01", end_date: "2023-12-31" };
    await runCorrelation(req);
    expect(api.post).toHaveBeenCalledWith("/backtest/correlation", req);
  });
});

describe("api/dividends", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchMonthlyOptimization calls GET /dividends/monthly-optimization", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchMonthlyOptimization();
    expect(api.get).toHaveBeenCalledWith("/dividends/monthly-optimization");
  });
});

describe("api/insights", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchInsights calls GET /insights", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchInsights();
    expect(api.get).toHaveBeenCalledWith("/insights");
  });
});

describe("api/risk", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchPortfolioRisk calls GET /portfolio/risk without portfolioId", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchPortfolioRisk();
    expect(api.get).toHaveBeenCalledWith("/portfolio/risk");
  });

  it("fetchPortfolioRisk calls GET /portfolio/risk with portfolio_id param when portfolioId given", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchPortfolioRisk("port-1");
    expect(api.get).toHaveBeenCalledWith("/portfolio/risk", { params: { portfolio_id: "port-1" } });
  });

  it("fetchRebalancingStrategy calls GET /portfolio/rebalancing-strategy", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchRebalancingStrategy("port-1");
    expect(api.get).toHaveBeenCalledWith("/portfolio/rebalancing-strategy?portfolio_id=port-1");
  });
});

describe("api/economicIndicators", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchInflationSummary calls GET /economic-indicators/inflation-summary", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    await fetchInflationSummary();
    expect(api.get).toHaveBeenCalledWith("/economic-indicators/inflation-summary");
  });
});
