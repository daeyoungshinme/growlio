import { describe, it, expect } from "vitest";
import { calcTradeKrw, calcSignedTradeKrw } from "../rebalancingTradeMath";
import type { RebalancingItem } from "@/api/rebalancing";

function makeItem(overrides: Partial<RebalancingItem> = {}): RebalancingItem {
  return {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    target_weight_pct: 10,
    current_weight_pct: 5,
    weight_diff_pct: 5,
    current_value_krw: 1000000,
    target_value_krw: 2000000,
    diff_krw: 1000000,
    shares_to_trade: null,
    current_price_krw: null,
    ...overrides,
  };
}

describe("calcTradeKrw", () => {
  it("shares_to_trade가 null이면 diff_krw의 절댓값 반환", () => {
    const item = makeItem({ shares_to_trade: null, diff_krw: -500000 });
    expect(calcTradeKrw(item)).toBe(500000);
  });

  it("current_price_krw가 0 이하이면 diff_krw의 절댓값 반환", () => {
    const item = makeItem({ shares_to_trade: 10, current_price_krw: 0, diff_krw: -300000 });
    expect(calcTradeKrw(item)).toBe(300000);
  });

  it("shares_to_trade와 current_price_krw가 모두 유효하면 반올림된 주수 기준 거래금액 반환", () => {
    const item = makeItem({ shares_to_trade: 3.4, current_price_krw: 70000, diff_krw: 200000 });
    expect(calcTradeKrw(item)).toBe(3 * 70000);
  });
});

describe("calcSignedTradeKrw", () => {
  it("shares_to_trade가 null이면 diff_krw 그대로 반환", () => {
    const item = makeItem({ shares_to_trade: null, diff_krw: -500000 });
    expect(calcSignedTradeKrw(item)).toBe(-500000);
  });

  it("current_price_krw가 0 이하이면 diff_krw 그대로 반환", () => {
    const item = makeItem({ shares_to_trade: 10, current_price_krw: 0, diff_krw: 300000 });
    expect(calcSignedTradeKrw(item)).toBe(300000);
  });

  it("shares_to_trade와 current_price_krw가 모두 유효하면 diff_krw 부호를 반영한 거래금액 반환", () => {
    const item = makeItem({ shares_to_trade: 3.4, current_price_krw: 70000, diff_krw: -200000 });
    expect(calcSignedTradeKrw(item)).toBe(-3 * 70000);
  });
});
