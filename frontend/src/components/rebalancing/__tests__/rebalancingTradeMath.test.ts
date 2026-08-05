import { describe, it, expect } from "vitest";
import {
  calcTradeKrw,
  calcSignedTradeKrw,
  calcTradeSummary,
  isTradableItem,
} from "../rebalancingTradeMath";
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

describe("isTradableItem", () => {
  it("shares_to_trade가 null이면 거래 불가(false) — CASH/부동산 등", () => {
    const item = makeItem({ shares_to_trade: null, current_price_krw: null, diff_krw: 30000000 });
    expect(isTradableItem(item)).toBe(false);
  });

  it("current_price_krw가 0 이하이면 거래 불가(false)", () => {
    const item = makeItem({ shares_to_trade: 5, current_price_krw: 0 });
    expect(isTradableItem(item)).toBe(false);
  });

  it("shares_to_trade와 current_price_krw가 모두 유효하면 거래 가능(true)", () => {
    const item = makeItem({ shares_to_trade: 5, current_price_krw: 70000 });
    expect(isTradableItem(item)).toBe(true);
  });
});

describe("calcTradeSummary", () => {
  it("CASH/부동산처럼 shares_to_trade가 null인 항목은 diff_krw가 아무리 커도 합계에서 제외", () => {
    const items: RebalancingItem[] = [
      makeItem({
        ticker: "CASH",
        shares_to_trade: null,
        current_price_krw: null,
        diff_krw: 30000000, // 거래 불가 항목의 큰 양수 diff — 매수 합계에 섞이면 안 됨
      }),
      makeItem({
        ticker: "KR_PROPERTY",
        shares_to_trade: null,
        current_price_krw: null,
        diff_krw: -50000000, // 거래 불가 항목의 큰 음수 diff — 매도 합계에 섞이면 안 됨
      }),
    ];
    const { totalBuySummary, totalSellSummary } = calcTradeSummary(items);
    expect(totalBuySummary).toBe(0);
    expect(totalSellSummary).toBe(0);
  });

  it("일반 주식 항목(shares_to_trade 유효)만 매수/매도 합계에 정상 반영", () => {
    const items: RebalancingItem[] = [
      makeItem({
        ticker: "005930",
        shares_to_trade: 10,
        current_price_krw: 70000,
        diff_krw: 700000,
      }),
      makeItem({
        ticker: "000660",
        shares_to_trade: -5,
        current_price_krw: 100000,
        diff_krw: -500000,
      }),
      makeItem({
        ticker: "CASH",
        shares_to_trade: null,
        current_price_krw: null,
        diff_krw: 10000000,
      }),
    ];
    const { totalBuySummary, totalSellSummary } = calcTradeSummary(items);
    expect(totalBuySummary).toBe(10 * 70000);
    expect(totalSellSummary).toBe(5 * 100000);
  });
});
