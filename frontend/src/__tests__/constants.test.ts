import { describe, it, expect } from "vitest";
import { QUERY_KEYS } from "@/constants/queryKeys";
import {
  DOMESTIC_MARKETS,
  OVERSEAS_MARKETS,
  OVERSEAS_MARKET_SET,
  POSITION_MARKETS,
  isOverseasMarket,
} from "@/constants/markets";
import { BACKTEST_DEFAULT_END_DATE, BACKTEST_DEFAULT_START_DATE } from "@/constants/defaults";
import { STALE_TIME, REFETCH_INTERVAL, PERSIST_CACHE_KEY } from "@/constants/queryConfig";
import { ASSET_MANAGEMENT_TABS, PORTFOLIO_TABS } from "@/constants/tabs";

// ────────────────────────────────────────────
// queryKeys
// ────────────────────────────────────────────
describe("QUERY_KEYS", () => {
  it("정적 키들이 배열 형태로 정의되어 있다", () => {
    expect(QUERY_KEYS.dashboard).toEqual(["dashboard"]);
    expect(QUERY_KEYS.portfolioOverview).toEqual(["portfolio-overview"]);
    expect(QUERY_KEYS.portfolioOverviewLite).toEqual(["portfolio-overview", "lite"]);
    expect(QUERY_KEYS.portfolios).toEqual(["portfolios"]);
    expect(QUERY_KEYS.accounts).toEqual(["accounts"]);
    expect(QUERY_KEYS.transactionsAll).toEqual(["transactions", "all"]);
    expect(QUERY_KEYS.dividendByTicker).toEqual(["dividend-by-ticker"]);
    expect(QUERY_KEYS.dividendSummary).toEqual(["dividend-summary"]);
    expect(QUERY_KEYS.dividendPositions).toEqual(["dividend-positions"]);
    expect(QUERY_KEYS.dcaAnalysis).toEqual(["dca-analysis"]);
    expect(QUERY_KEYS.settings).toEqual(["settings"]);
    expect(QUERY_KEYS.exchangeRate).toEqual(["exchange-rate"]);
    expect(QUERY_KEYS.exchangeRateAlerts).toEqual(["exchange-rate-alerts"]);
    expect(QUERY_KEYS.stockPriceAlerts).toEqual(["stock-price-alerts"]);
    expect(QUERY_KEYS.rebalancingAlerts).toEqual(["rebalancing-alerts"]);
    expect(QUERY_KEYS.rebalancingHistory).toEqual(["rebalancing-history"]);
    expect(QUERY_KEYS.alertHistory).toEqual(["alert-history"]);
    expect(QUERY_KEYS.insights).toEqual(["insights"]);
    expect(QUERY_KEYS.insightsSummary).toEqual(["insights", "summary"]);
    expect(QUERY_KEYS.monthlyOptimization).toEqual(["monthly-optimization"]);
    expect(QUERY_KEYS.marketSignal).toEqual(["market-signal"]);
    expect(QUERY_KEYS.factorAnalysis).toEqual(["factor-analysis"]);
    expect(QUERY_KEYS.overseasPositionsTax).toEqual(["overseas-positions-tax"]);
  });

  it("동적 키 팩토리 함수들이 올바른 키를 반환한다", () => {
    expect(QUERY_KEYS.accountPositions("acc-1")).toEqual(["account-positions", "acc-1"]);
    expect(QUERY_KEYS.transactions("acc-2")).toEqual(["transactions", "acc-2"]);
    expect(QUERY_KEYS.allTransactions(2024)).toEqual(["transactions", "all", 2024]);
    expect(QUERY_KEYS.rebalancingAlert("port-1")).toEqual(["rebalancing-alert", "port-1"]);
    expect(QUERY_KEYS.taxSummary(2024)).toEqual(["tax-summary", 2024]);
    expect(QUERY_KEYS.dartDisclosures(30)).toEqual(["dart-disclosures", 30]);
    expect(QUERY_KEYS.allocationHistory(12)).toEqual(["allocation-history", 12]);
    expect(QUERY_KEYS.portfolioRisk("p-1")).toEqual(["portfolio-risk", "p-1"]);
    expect(QUERY_KEYS.portfolioFactorAnalysis("p-2")).toEqual(["factor-analysis", "p-2"]);
    expect(QUERY_KEYS.rebalancingStrategy("p-3")).toEqual(["rebalancing-strategy", "p-3"]);
  });

  it("efficientFrontier는 comparePortfolioId 없으면 null을 포함한다", () => {
    expect(QUERY_KEYS.efficientFrontier()).toEqual(["efficient-frontier", null]);
    expect(QUERY_KEYS.efficientFrontier("p-1")).toEqual(["efficient-frontier", "p-1"]);
  });
});

// ────────────────────────────────────────────
// markets
// ────────────────────────────────────────────
describe("markets constants", () => {
  it("DOMESTIC_MARKETS는 국내 거래소 3개를 포함한다", () => {
    expect(DOMESTIC_MARKETS).toContain("KOSPI");
    expect(DOMESTIC_MARKETS).toContain("KOSDAQ");
    expect(DOMESTIC_MARKETS).toContain("KRX");
    expect(DOMESTIC_MARKETS).toHaveLength(3);
  });

  it("OVERSEAS_MARKETS는 미국 거래소들을 포함한다", () => {
    expect(OVERSEAS_MARKETS).toContain("NYSE");
    expect(OVERSEAS_MARKETS).toContain("NASDAQ");
    expect(OVERSEAS_MARKETS).toContain("AMEX");
  });

  it("POSITION_MARKETS에는 주요 거래소 5개가 포함된다", () => {
    expect(POSITION_MARKETS).toContain("KOSPI");
    expect(POSITION_MARKETS).toContain("KOSDAQ");
    expect(POSITION_MARKETS).toContain("NYSE");
    expect(POSITION_MARKETS).toContain("NASDAQ");
    expect(POSITION_MARKETS).toContain("AMEX");
    expect(POSITION_MARKETS).toHaveLength(5);
  });

  it("OVERSEAS_MARKET_SET은 Set 인스턴스이다", () => {
    expect(OVERSEAS_MARKET_SET).toBeInstanceOf(Set);
    expect(OVERSEAS_MARKET_SET.has("NYSE")).toBe(true);
    expect(OVERSEAS_MARKET_SET.has("KOSPI")).toBe(false);
  });

  it("isOverseasMarket — 해외 거래소를 올바르게 판별한다", () => {
    expect(isOverseasMarket("NYSE")).toBe(true);
    expect(isOverseasMarket("NASDAQ")).toBe(true);
    expect(isOverseasMarket("AMEX")).toBe(true);
    expect(isOverseasMarket("NYSE_US")).toBe(true);
    expect(isOverseasMarket("nasdaq_us")).toBe(true);
  });

  it("isOverseasMarket — 국내 거래소는 false를 반환한다", () => {
    expect(isOverseasMarket("KOSPI")).toBe(false);
    expect(isOverseasMarket("KOSDAQ")).toBe(false);
    expect(isOverseasMarket("KRX")).toBe(false);
  });
});

// ────────────────────────────────────────────
// defaults
// ────────────────────────────────────────────
describe("backtest defaults", () => {
  it("BACKTEST_DEFAULT_END_DATE는 YYYY-MM-DD 형식이다", () => {
    expect(BACKTEST_DEFAULT_END_DATE).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("BACKTEST_DEFAULT_START_DATE는 현재 연도 기준 5년 전 1월 1일이다", () => {
    const expectedYear = new Date().getFullYear() - 5;
    expect(BACKTEST_DEFAULT_START_DATE).toBe(`${expectedYear}-01-01`);
  });
});

// ────────────────────────────────────────────
// queryConfig
// ────────────────────────────────────────────
describe("queryConfig constants", () => {
  it("PERSIST_CACHE_KEY가 정의되어 있다", () => {
    expect(PERSIST_CACHE_KEY).toBe("rq-persist-cache");
  });

  it("STALE_TIME 값들이 양수 밀리초이다", () => {
    expect(STALE_TIME.SHORT).toBeGreaterThan(0);
    expect(STALE_TIME.MEDIUM).toBeGreaterThan(STALE_TIME.SHORT);
    expect(STALE_TIME.LONG).toBeGreaterThan(STALE_TIME.MEDIUM);
    expect(STALE_TIME.EXCHANGE_RATE).toBeGreaterThan(0);
  });

  it("STALE_TIME 구체적 값이 의도한 단위와 일치한다", () => {
    expect(STALE_TIME.SHORT).toBe(30_000);
    expect(STALE_TIME.MEDIUM).toBe(60_000);
    expect(STALE_TIME.LONG).toBe(1000 * 60 * 60);
    expect(STALE_TIME.EXCHANGE_RATE).toBe(5 * 60 * 1000);
  });

  it("REFETCH_INTERVAL 값들이 양수 밀리초이다", () => {
    expect(REFETCH_INTERVAL.DASHBOARD).toBeGreaterThan(0);
    expect(REFETCH_INTERVAL.PORTFOLIO).toBeGreaterThan(0);
  });
});

// ────────────────────────────────────────────
// tabs
// ────────────────────────────────────────────
describe("tabs constants", () => {
  it("ASSET_MANAGEMENT_TABS는 4개 탭을 포함한다", () => {
    expect(ASSET_MANAGEMENT_TABS).toHaveLength(4);
    expect(ASSET_MANAGEMENT_TABS).toContain("은행계좌");
    expect(ASSET_MANAGEMENT_TABS).toContain("증권계좌");
    expect(ASSET_MANAGEMENT_TABS).toContain("부동산");
    expect(ASSET_MANAGEMENT_TABS).toContain("입출금·배당");
  });

  it("PORTFOLIO_TABS는 4개 탭을 포함한다", () => {
    expect(PORTFOLIO_TABS).toHaveLength(4);
    expect(PORTFOLIO_TABS).toContain("종목 현황");
    expect(PORTFOLIO_TABS).toContain("배당");
    expect(PORTFOLIO_TABS).toContain("세금");
    expect(PORTFOLIO_TABS).toContain("진단");
  });
});
