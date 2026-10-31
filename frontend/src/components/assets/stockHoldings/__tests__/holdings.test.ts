import { describe, it, expect } from "vitest";
import type { DividendYield } from "@/types";
import { annualDividendLabel } from "../holdings";

function makeDiv(overrides: Partial<DividendYield> = {}): DividendYield {
  return {
    ticker: "005930",
    market: "KOSPI",
    dividend_yield: 2,
    dps: 1444,
    ex_dividend_date: null,
    estimated_annual_krw: 0,
    estimated_monthly_krw: 0,
    dividend_months: [],
    investment_yield: 0,
    ...overrides,
  };
}

describe("annualDividendLabel", () => {
  it("국내 종목은 원 단위로 반올림한다", () => {
    expect(annualDividendLabel(makeDiv({ dps: 361.5 }), 3)).toBe(`${(1085).toLocaleString()}원`);
  });

  it("해외 종목은 달러로 표시한다", () => {
    expect(annualDividendLabel(makeDiv({ market: "nasdaq", dps: 1.25 }), 4)).toBe("$5");
  });

  it("주당 배당이 없으면 null", () => {
    expect(annualDividendLabel(makeDiv({ dps: 0 }), 10)).toBeNull();
  });
});
