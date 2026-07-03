import { describe, it, expect, vi, beforeEach } from "vitest";

// ── mocks ────────────────────────────────────────────────────────────────────

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

// ── imports ───────────────────────────────────────────────────────────────────

import { api } from "@/api/client";
import { fetchMarketSignal } from "@/api/marketSignals";
import { fetchDCAAnalysis } from "@/api/invest";
import { fetchPortfolioRisk } from "@/api/risk";
import {
  fetchBacktestPortfolios,
  createBacktestPortfolio,
  updateBacktestPortfolio,
  deleteBacktestPortfolio,
  runBacktest,
  runCorrelation,
} from "@/api/backtest";
import { fetchOverseasPositionsTax, fetchTaxSummary } from "@/api/tax";

// ── api/marketSignals ─────────────────────────────────────────────────────────

describe("api/marketSignals", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchMarketSignal calls GET /market-signals", async () => {
    const mockSignal = {
      composite_level: "GREEN" as const,
      composite_score: 75,
      fear_greed_contrarian_buy: false,
      fear_greed_extreme_greed: false,
      signals: { vix: null, yield_curve: null, fear_greed: null },
      computed_at: "2024-01-01T00:00:00Z",
      data_freshness: "LIVE" as const,
    };
    vi.mocked(api.get).mockResolvedValue({ data: mockSignal });
    const result = await fetchMarketSignal();
    expect(api.get).toHaveBeenCalledWith("/market-signals");
    expect(result).toEqual(mockSignal);
  });

  it("RED 리스크 레벨을 올바르게 반환한다", async () => {
    const mockSignal = {
      composite_level: "RED" as const,
      composite_score: 20,
      fear_greed_contrarian_buy: true,
      fear_greed_extreme_greed: false,
      signals: {
        vix: { value: 35, level: "HIGH" as const, date: "2024-01-01", sub_score: 10 },
        yield_curve: null,
        fear_greed: {
          value: 15,
          classification: "EXTREME_FEAR" as const,
          label: "극도의 공포",
          label_en: "Extreme Fear",
          sub_score: 5,
        },
      },
      computed_at: "2024-01-01T00:00:00Z",
      data_freshness: "CACHED" as const,
    };
    vi.mocked(api.get).mockResolvedValue({ data: mockSignal });
    const result = await fetchMarketSignal();
    expect(result.composite_level).toBe("RED");
    expect(result.fear_greed_contrarian_buy).toBe(true);
  });

  it("YELLOW 리스크 레벨을 올바르게 반환한다", async () => {
    const mockSignal = {
      composite_level: "YELLOW" as const,
      composite_score: 50,
      fear_greed_contrarian_buy: false,
      fear_greed_extreme_greed: false,
      signals: {
        vix: { value: 22, level: "MEDIUM" as const, date: "2024-01-01", sub_score: 50 },
        yield_curve: {
          value: -0.1,
          state: "FLAT" as const,
          date: "2024-01-01",
          sub_score: 50,
        },
        fear_greed: null,
      },
      computed_at: "2024-01-01T00:00:00Z",
      data_freshness: "PARTIAL" as const,
    };
    vi.mocked(api.get).mockResolvedValue({ data: mockSignal });
    const result = await fetchMarketSignal();
    expect(result.composite_level).toBe("YELLOW");
    expect(result.signals.vix?.level).toBe("MEDIUM");
  });
});

// ── api/invest ────────────────────────────────────────────────────────────────

describe("api/invest", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchDCAAnalysis calls GET /invest/dca-analysis", async () => {
    const mockData = {
      settings: {
        monthly_deposit_amount: 500000,
        goal_annual_return_pct: 8,
        goal_amount: 100000000,
        goal_start_date: "2024-01-01",
        goal_initial_amount: null,
      },
      projection_months: [],
      yearly_achievements: [],
      goal_timeline: {
        months_to_goal: null,
        expected_goal_date: null,
        actual_expected_goal_date: null,
        current_progress_pct: 30,
        on_track: null,
        lead_lag_months: null,
      },
      is_configured: true,
    };
    vi.mocked(api.get).mockResolvedValue({ data: mockData });
    const result = await fetchDCAAnalysis();
    expect(api.get).toHaveBeenCalledWith("/invest/dca-analysis");
    expect(result).toEqual(mockData);
  });
});

// ── api/risk ──────────────────────────────────────────────────────────────────

describe("api/risk", () => {
  beforeEach(() => vi.clearAllMocks());

  const mockRisk = {
    var_95_pct: -5.2,
    var_99_pct: -8.1,
    annualized_volatility_pct: 15.3,
    beta_sp500: 1.1,
    diversification_score: 0.75,
    top_holding_weight_pct: 25,
    position_count: 10,
    data_available: true,
    note: "",
  };

  it("fetchPortfolioRisk calls GET /portfolio/risk without portfolioId", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockRisk });
    const result = await fetchPortfolioRisk();
    expect(api.get).toHaveBeenCalledWith("/portfolio/risk");
    expect(result).toEqual(mockRisk);
  });

  it("fetchPortfolioRisk calls GET /portfolio/risk/:id with portfolioId", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: mockRisk });
    const result = await fetchPortfolioRisk("p123");
    expect(api.get).toHaveBeenCalledWith("/portfolio/risk/p123");
    expect(result).toEqual(mockRisk);
  });
});

// ── api/backtest ──────────────────────────────────────────────────────────────

describe("api/backtest", () => {
  beforeEach(() => vi.clearAllMocks());

  const mockPortfolio = {
    id: "bt1",
    name: "Test Portfolio",
    holdings: [{ ticker: "005930", market: "KRX", weight: 100 }],
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
  };

  it("fetchBacktestPortfolios calls GET /backtest/portfolios", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [mockPortfolio] });
    const result = await fetchBacktestPortfolios();
    expect(api.get).toHaveBeenCalledWith("/backtest/portfolios");
    expect(result).toEqual([mockPortfolio]);
  });

  it("createBacktestPortfolio calls POST /backtest/portfolios", async () => {
    vi.mocked(api.post).mockResolvedValue({ data: mockPortfolio });
    const body = {
      name: "Test Portfolio",
      holdings: [{ ticker: "005930", market: "KRX", weight: 100 }],
    };
    const result = await createBacktestPortfolio(body);
    expect(api.post).toHaveBeenCalledWith("/backtest/portfolios", body);
    expect(result).toEqual(mockPortfolio);
  });

  it("updateBacktestPortfolio calls PUT /backtest/portfolios/:id", async () => {
    vi.mocked(api.put).mockResolvedValue({ data: mockPortfolio });
    const result = await updateBacktestPortfolio("bt1", { name: "Updated" });
    expect(api.put).toHaveBeenCalledWith("/backtest/portfolios/bt1", { name: "Updated" });
    expect(result).toEqual(mockPortfolio);
  });

  it("deleteBacktestPortfolio calls DELETE /backtest/portfolios/:id", async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: undefined });
    await deleteBacktestPortfolio("bt1");
    expect(api.delete).toHaveBeenCalledWith("/backtest/portfolios/bt1");
  });

  it("runBacktest calls POST /backtest/run", async () => {
    const mockResult = { dates: ["2024-01-01"], series: [], metrics: [] };
    vi.mocked(api.post).mockResolvedValue({ data: mockResult });
    const req = {
      portfolio_ids: ["bt1"],
      start_date: "2023-01-01",
      end_date: "2024-01-01",
      include_spy: true,
      include_real_portfolio: false,
      reinvest_dividends: true,
    };
    const result = await runBacktest(req);
    expect(api.post).toHaveBeenCalledWith("/backtest/run", req);
    expect(result).toEqual(mockResult);
  });

  it("runCorrelation calls POST /backtest/correlation", async () => {
    const mockCorrelation = {
      labels: ["Portfolio A", "SPY"],
      matrix: [
        [1, 0.8],
        [0.8, 1],
      ],
    };
    vi.mocked(api.post).mockResolvedValue({ data: mockCorrelation });
    const req = {
      portfolio_ids: ["bt1"],
      start_date: "2023-01-01",
      end_date: "2024-01-01",
    };
    const result = await runCorrelation(req);
    expect(api.post).toHaveBeenCalledWith("/backtest/correlation", req);
    expect(result).toEqual(mockCorrelation);
  });
});

// ── api/tax ───────────────────────────────────────────────────────────────────

describe("api/tax", () => {
  beforeEach(() => vi.clearAllMocks());

  it("fetchOverseasPositionsTax calls GET /tax/overseas-positions", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [] });
    const result = await fetchOverseasPositionsTax();
    expect(api.get).toHaveBeenCalledWith("/tax/overseas-positions");
    expect(result).toEqual([]);
  });

  it("fetchTaxSummary calls GET /tax/summary without year", async () => {
    const mockSummary = {
      year: 2024,
      dividend_income_krw: 1000000,
      dividend_tax_krw: 154000,
      overseas_unrealized_gain_krw: 5000000,
      overseas_gain_deduction_krw: 2500000,
      overseas_tax_estimated_krw: 462000,
      domestic_stock_value_krw: 0,
      domestic_large_holder_warning: false,
      comprehensive_tax_warning: false,
      total_estimated_tax_krw: 616000,
      note: "",
      rates: { dividend_tax_rate_pct: 15.4, overseas_tax_rate_pct: 22 },
    };
    vi.mocked(api.get).mockResolvedValue({ data: mockSummary });
    const result = await fetchTaxSummary();
    expect(api.get).toHaveBeenCalledWith("/tax/summary", { params: undefined });
    expect(result).toEqual(mockSummary);
  });

  it("fetchTaxSummary calls GET /tax/summary with year", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
    await fetchTaxSummary(2023);
    expect(api.get).toHaveBeenCalledWith("/tax/summary", { params: { year: 2023 } });
  });
});
