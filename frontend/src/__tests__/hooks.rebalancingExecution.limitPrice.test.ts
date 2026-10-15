import { describe, expect, it } from "vitest";
import type { ExecutionOrderItem } from "@/api/rebalancing";
import { findMissingLimitPriceTickers } from "@/hooks/useRebalancingExecution";

const order = (over: Partial<ExecutionOrderItem>): ExecutionOrderItem => ({
  ticker: "AAPL",
  name: "Apple",
  market: "NASDAQ",
  side: "BUY",
  quantity: 1,
  account_id: "acc",
  order_type: "LIMIT",
  limit_price: 200,
  ...over,
});

describe("findMissingLimitPriceTickers", () => {
  it("지정가 주문 중 가격이 없거나 0인 종목만 돌려준다", () => {
    const orders = [
      order({}),
      order({ ticker: "MSFT", limit_price: null }),
      order({ ticker: "005930", market: "KOSPI", limit_price: 0 }),
    ];
    expect(findMissingLimitPriceTickers(orders)).toEqual(["MSFT", "005930"]);
  });

  it("시장가 주문은 가격이 없어도 문제없다", () => {
    expect(
      findMissingLimitPriceTickers([order({ order_type: "MARKET", limit_price: null })]),
    ).toEqual([]);
  });
});
