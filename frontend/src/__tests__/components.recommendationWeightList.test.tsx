import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import RecommendationWeightList from "@/components/rebalancing/RecommendationWeightList";
import { CASH_EQUIVALENT_TICKER, type GoalRecommendationItem } from "@/api/rebalancing";

function makeItem(overrides: Partial<GoalRecommendationItem> = {}): GoalRecommendationItem {
  return {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI",
    weight: 25.5,
    dividend_yield_pct: null,
    ...overrides,
  } as GoalRecommendationItem;
}

describe("RecommendationWeightList", () => {
  it("종목명과 비중을 표시한다", () => {
    renderWithProviders(<RecommendationWeightList items={[makeItem()]} />);
    expect(screen.getByText("삼성전자")).toBeInTheDocument();
    expect(screen.getByText("25.5%")).toBeInTheDocument();
  });

  it("일반 티커는 괄호로 표시한다", () => {
    renderWithProviders(<RecommendationWeightList items={[makeItem()]} />);
    expect(screen.getByText("(005930)")).toBeInTheDocument();
  });

  it("현금성 자산 합성 티커는 괄호 표기를 생략한다", () => {
    renderWithProviders(
      <RecommendationWeightList
        items={[makeItem({ ticker: CASH_EQUIVALENT_TICKER, name: "현금성 자산" })]}
      />,
    );
    expect(screen.queryByText(`(${CASH_EQUIVALENT_TICKER})`)).toBeNull();
  });

  it("배당수익률이 있으면 함께 표시한다", () => {
    renderWithProviders(
      <RecommendationWeightList items={[makeItem({ dividend_yield_pct: 3.2 })]} />,
    );
    expect(screen.getByText(/배당 3.2%/)).toBeInTheDocument();
  });

  it("배당수익률이 없으면 표시하지 않는다", () => {
    renderWithProviders(
      <RecommendationWeightList items={[makeItem({ dividend_yield_pct: null })]} />,
    );
    expect(screen.queryByText(/배당/)).toBeNull();
  });
});
