import { describe, it, expect } from "vitest";
import { groupPositionsByTicker } from "../portfolio";
import type { PortfolioPosition } from "@/types";

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
