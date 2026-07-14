import { describe, it, expect } from "vitest";
import {
  getPortfolioHorizon,
  getPortfolioHorizonTaxType,
  groupPositionsByTicker,
  mergeAlertsByPortfolio,
} from "../portfolio";
import type { PortfolioPosition } from "@/types";
import type { RebalancingAlert } from "@/api/alerts";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";

function makePos(overrides: Partial<PortfolioPosition> = {}): PortfolioPosition {
  return {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    qty: 10,
    avg_price: 70000,
    current_price: 75000,
    value_krw: 750000,
    invested_krw: 700000,
    pnl: 50000,
    pnl_pct: 7.14,
    currency: "KRW",
    account_id: "acc-1",
    account_name: "테스트 계좌",
    weight_in_stock: 20,
    ...overrides,
  };
}

describe("groupPositionsByTicker", () => {
  it("빈 배열이면 빈 배열 반환", () => {
    expect(groupPositionsByTicker([])).toEqual([]);
  });

  it("단일 포지션은 그대로 집계", () => {
    const result = groupPositionsByTicker([makePos()]);
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe("005930");
    expect(result[0].total_qty).toBe(10);
    expect(result[0].sub_positions).toHaveLength(1);
  });

  it("같은 ticker+market은 합산", () => {
    const positions = [
      makePos({
        account_id: "acc-1",
        qty: 10,
        value_krw: 750000,
        invested_krw: 700000,
        pnl: 50000,
        weight_in_stock: 10,
      }),
      makePos({
        account_id: "acc-2",
        qty: 5,
        value_krw: 375000,
        invested_krw: 350000,
        pnl: 25000,
        weight_in_stock: 5,
      }),
    ];
    const result = groupPositionsByTicker(positions);
    expect(result).toHaveLength(1);
    expect(result[0].total_qty).toBe(15);
    expect(result[0].total_value_krw).toBe(1125000);
    expect(result[0].total_invested_krw).toBe(1050000);
    expect(result[0].total_pnl).toBe(75000);
    expect(result[0].sub_positions).toHaveLength(2);
  });

  it("다른 ticker는 별도 집계", () => {
    const positions = [
      makePos({ ticker: "005930", market: "KOSPI" }),
      makePos({ ticker: "AAPL", market: "NASDAQ" }),
    ];
    const result = groupPositionsByTicker(positions);
    expect(result).toHaveLength(2);
  });

  it("같은 ticker라도 market 다르면 별도 집계", () => {
    const positions = [
      makePos({ ticker: "APPLE", market: "KOSPI" }),
      makePos({ ticker: "APPLE", market: "NASDAQ" }),
    ];
    const result = groupPositionsByTicker(positions);
    expect(result).toHaveLength(2);
  });

  it("pnl_pct 올바르게 계산", () => {
    const positions = [
      makePos({ qty: 10, value_krw: 1100000, invested_krw: 1000000, pnl: 100000 }),
    ];
    const result = groupPositionsByTicker(positions);
    expect(result[0].pnl_pct).toBeCloseTo(10.0);
  });

  it("invested_krw가 0이면 pnl_pct는 0", () => {
    const positions = [makePos({ invested_krw: 0, pnl: 0 })];
    const result = groupPositionsByTicker(positions);
    expect(result[0].pnl_pct).toBe(0);
  });
});

function makeAlert(overrides: Partial<RebalancingAlert> = {}): RebalancingAlert {
  return {
    id: "alert-1",
    portfolio_id: "portfolio-1",
    is_active: true,
    threshold_pct: 5,
    schedule_type: "DAILY",
    schedule_day_of_week: null,
    schedule_day_of_month: null,
    trigger_condition: "SCHEDULE",
    mode: "NOTIFY",
    strategy: "FULL",
    account_id: null,
    order_type: "MARKET",
    market_condition_mode: "IGNORE",
    auto_execution_time: null,
    notify_time: "08:30",
    ...overrides,
  } as RebalancingAlert;
}

describe("mergeAlertsByPortfolio", () => {
  it("빈 배열이면 빈 객체 반환", () => {
    expect(mergeAlertsByPortfolio([])).toEqual({});
  });

  it("포트폴리오별로 1개 행이면 그대로 반환", () => {
    const alert = makeAlert({ portfolio_id: "p1", mode: "NOTIFY" });
    const result = mergeAlertsByPortfolio([alert]);
    expect(result["p1"].mode).toBe("NOTIFY");
  });

  it("같은 포트폴리오에 AUTO 계좌가 하나라도 있으면 병합 결과는 AUTO", () => {
    const alerts = [
      makeAlert({ id: "a1", portfolio_id: "p1", account_id: "acc-1", mode: "NOTIFY" }),
      makeAlert({ id: "a2", portfolio_id: "p1", account_id: "acc-2", mode: "AUTO" }),
    ];
    const result = mergeAlertsByPortfolio(alerts);
    expect(Object.keys(result)).toHaveLength(1);
    expect(result["p1"].mode).toBe("AUTO");
  });

  it("모든 계좌가 NOTIFY면 병합 결과도 NOTIFY", () => {
    const alerts = [
      makeAlert({ id: "a1", portfolio_id: "p1", account_id: "acc-1", mode: "NOTIFY" }),
      makeAlert({ id: "a2", portfolio_id: "p1", account_id: "acc-2", mode: "NOTIFY" }),
    ];
    const result = mergeAlertsByPortfolio(alerts);
    expect(result["p1"].mode).toBe("NOTIFY");
  });

  it("서로 다른 포트폴리오는 각각 별도로 집계", () => {
    const alerts = [
      makeAlert({ id: "a1", portfolio_id: "p1", mode: "AUTO" }),
      makeAlert({ id: "a2", portfolio_id: "p2", mode: "NOTIFY" }),
    ];
    const result = mergeAlertsByPortfolio(alerts);
    expect(Object.keys(result)).toHaveLength(2);
    expect(result["p1"].mode).toBe("AUTO");
    expect(result["p2"].mode).toBe("NOTIFY");
  });
});

function makePortfolio(overrides: Partial<Portfolio> = {}): Portfolio {
  return {
    id: "portfolio-1",
    name: "테스트 포트폴리오",
    items: [],
    base_type: "STOCK_ONLY",
    account_ids: null,
    sort_order: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeAccount(overrides: Partial<AssetAccount> = {}): AssetAccount {
  return {
    id: "acc-1",
    name: "테스트 계좌",
    asset_type: "STOCK_KIS",
    data_source: "KIS_API",
    institution: null,
    kis_account_no: null,
    kiwoom_account_no: null,
    is_mock_mode: false,
    manual_amount: null,
    manual_currency: "KRW",
    manual_updated_at: null,
    deposit_krw: null,
    deposit_usd: null,
    real_estate_details: null,
    include_in_total: true,
    is_active: true,
    sort_order: 0,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    has_own_kis_credentials: false,
    has_own_kiwoom_credentials: false,
    ...overrides,
  };
}

describe("getPortfolioHorizon", () => {
  it("목표 지정된 계좌가 없으면 null", () => {
    const portfolio = makePortfolio();
    const accounts = [makeAccount({ id: "acc-1", investment_horizon: "SHORT_TERM" })];
    expect(getPortfolioHorizon(portfolio, accounts)).toBeNull();
  });

  it("목표 지정된 계좌가 전부 같은 기간이면 그 기간을 반환", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({ id: "acc-1", target_portfolio_id: "p1", investment_horizon: "SHORT_TERM" }),
      makeAccount({ id: "acc-2", target_portfolio_id: "p1", investment_horizon: "SHORT_TERM" }),
    ];
    expect(getPortfolioHorizon(portfolio, accounts)).toBe("SHORT_TERM");
  });

  it("목표 지정된 계좌의 기간이 섞여 있으면 null", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({ id: "acc-1", target_portfolio_id: "p1", investment_horizon: "SHORT_TERM" }),
      makeAccount({ id: "acc-2", target_portfolio_id: "p1", investment_horizon: "LONG_TERM" }),
    ];
    expect(getPortfolioHorizon(portfolio, accounts)).toBeNull();
  });

  it("목표 지정된 계좌에 기간 태그가 없으면 null", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({ id: "acc-1", target_portfolio_id: "p1", investment_horizon: null }),
    ];
    expect(getPortfolioHorizon(portfolio, accounts)).toBeNull();
  });

  it("다른 포트폴리오를 목표로 지정한 계좌는 무시", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({ id: "acc-1", target_portfolio_id: "p2", investment_horizon: "SHORT_TERM" }),
    ];
    expect(getPortfolioHorizon(portfolio, accounts)).toBeNull();
  });
});

describe("getPortfolioHorizonTaxType", () => {
  it("목표 지정된 계좌가 없으면 null", () => {
    const portfolio = makePortfolio();
    const accounts = [
      makeAccount({ id: "acc-1", investment_horizon: "SHORT_TERM", tax_type: "ISA" }),
    ];
    expect(getPortfolioHorizonTaxType(portfolio, accounts)).toBeNull();
  });

  it("목표 지정된 계좌가 전부 같은 기간·세제유형이면 그 조합을 반환", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({
        id: "acc-1",
        target_portfolio_id: "p1",
        investment_horizon: "LONG_TERM",
        tax_type: "ISA",
      }),
      makeAccount({
        id: "acc-2",
        target_portfolio_id: "p1",
        investment_horizon: "LONG_TERM",
        tax_type: "ISA",
      }),
    ];
    expect(getPortfolioHorizonTaxType(portfolio, accounts)).toEqual({
      horizon: "LONG_TERM",
      taxType: "ISA",
    });
  });

  it("기간은 같아도 세제유형이 섞여 있으면 null", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({
        id: "acc-1",
        target_portfolio_id: "p1",
        investment_horizon: "LONG_TERM",
        tax_type: "ISA",
      }),
      makeAccount({
        id: "acc-2",
        target_portfolio_id: "p1",
        investment_horizon: "LONG_TERM",
        tax_type: "GENERAL",
      }),
    ];
    expect(getPortfolioHorizonTaxType(portfolio, accounts)).toBeNull();
  });

  it("세제유형은 같아도 기간이 섞여 있으면 null", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({
        id: "acc-1",
        target_portfolio_id: "p1",
        investment_horizon: "SHORT_TERM",
        tax_type: "ISA",
      }),
      makeAccount({
        id: "acc-2",
        target_portfolio_id: "p1",
        investment_horizon: "LONG_TERM",
        tax_type: "ISA",
      }),
    ];
    expect(getPortfolioHorizonTaxType(portfolio, accounts)).toBeNull();
  });

  it("목표 지정된 계좌에 세제유형 태그가 없으면 null", () => {
    const portfolio = makePortfolio({ id: "p1" });
    const accounts = [
      makeAccount({
        id: "acc-1",
        target_portfolio_id: "p1",
        investment_horizon: "LONG_TERM",
        tax_type: undefined,
      }),
    ];
    expect(getPortfolioHorizonTaxType(portfolio, accounts)).toBeNull();
  });
});
