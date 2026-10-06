import { describe, it, expect } from "vitest";
import { formatRecMetricParts } from "@/components/rebalancing/recommendationCardModel";

const ALL = {
  required_dividend_yield_pct: 3.04,
  expected_return_pct: 7.25,
  expected_dividend_yield_pct: 2.5,
  expected_volatility_pct: 12.0,
};

describe("formatRecMetricParts", () => {
  it("값이 있는 지표만 고정 순서로 소수점 1자리 조각을 만든다", () => {
    expect(formatRecMetricParts(ALL)).toEqual([
      "목표 배당수익률 연 3.0%",
      "기대수익률 7.3%",
      "배당수익률 약 2.5%",
      "예상 변동성 연 12.0%",
    ]);
  });

  it("null 지표는 건너뛴다", () => {
    expect(
      formatRecMetricParts({
        ...ALL,
        required_dividend_yield_pct: null,
        expected_dividend_yield_pct: null,
      }),
    ).toEqual(["기대수익률 7.3%", "예상 변동성 연 12.0%"]);
  });

  it("includeExpected=false면 목표 배당수익률만 남긴다(추천 결과가 빈 기간별 탭)", () => {
    expect(formatRecMetricParts(ALL, false)).toEqual(["목표 배당수익률 연 3.0%"]);
  });
});
