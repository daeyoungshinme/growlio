import { describe, expect, it } from "vitest";
import type { PortfolioItem } from "@/api/portfolios";
import { getPortfolioItemsError, submittablePortfolioItems } from "@/hooks/usePortfolioItemsEditor";

const item = (ticker: string, weight: number): PortfolioItem => ({
  ticker,
  name: ticker,
  market: "KOSPI",
  weight,
});

describe("getPortfolioItemsError", () => {
  it("합계가 100이어도 음수 비중은 거부한다", () => {
    expect(getPortfolioItemsError([item("A", 110), item("B", -10)])).toMatch("0~100");
  });

  it("종목 없는 행에 비중이 있으면 거부한다", () => {
    expect(getPortfolioItemsError([item("A", 60), item("", 40)])).toMatch("종목을 선택하지 않은");
  });

  it("종목 없는 0% 빈 행은 허용하고 저장 대상에서 뺀다", () => {
    const items = [item("A", 100), item("", 0)];
    expect(getPortfolioItemsError(items)).toBeNull();
    expect(submittablePortfolioItems(items).map((i) => i.ticker)).toEqual(["A"]);
  });
});
