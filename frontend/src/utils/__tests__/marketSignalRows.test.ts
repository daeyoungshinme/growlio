import { describe, it, expect } from "vitest";
import { dotColorForSubScore, buildSignalRows } from "../marketSignalRows";
import type { MarketSignalResponse } from "@/api/marketSignals";

describe("dotColorForSubScore", () => {
  it("returns green for 0", () => {
    expect(dotColorForSubScore(0)).toBe("bg-green-500");
  });

  it("returns yellow for 1", () => {
    expect(dotColorForSubScore(1)).toBe("bg-yellow-500");
  });

  it("returns orange for 2", () => {
    expect(dotColorForSubScore(2)).toBe("bg-orange-500");
  });

  it("returns red for 3 and above", () => {
    expect(dotColorForSubScore(3)).toBe("bg-red-500");
    expect(dotColorForSubScore(4)).toBe("bg-red-500");
  });
});

const emptySignals: MarketSignalResponse["signals"] = {
  vix: null,
  us_rate_curve: null,
  high_yield_spread: null,
  dollar_index: null,
  exchange_rate: null,
  oil_price: null,
  inflation: null,
  employment: null,
};

describe("buildSignalRows", () => {
  it("returns 8 rows in fixed order with null content when no data", () => {
    const rows = buildSignalRows(emptySignals);
    expect(rows).toHaveLength(8);
    expect(rows.map((r) => r.key)).toEqual([
      "vix",
      "us_rate_curve",
      "high_yield_spread",
      "dollar_index",
      "exchange_rate",
      "oil_price",
      "inflation",
      "employment",
    ]);
    expect(rows.every((r) => r.content === null)).toBe(true);
  });

  it("assigns tier A to vix/high_yield_spread/employment and tier B/C to the rest", () => {
    const rows = buildSignalRows(emptySignals);
    const byKey = Object.fromEntries(rows.map((r) => [r.key, r.tier]));
    expect(byKey.vix).toBe("A");
    expect(byKey.high_yield_spread).toBe("A");
    expect(byKey.employment).toBe("A");
    expect(byKey.us_rate_curve).not.toBe("A");
    expect(byKey.dollar_index).not.toBe("A");
    expect(byKey.exchange_rate).not.toBe("A");
    expect(byKey.oil_price).not.toBe("A");
    expect(byKey.inflation).not.toBe("A");
  });

  it("picks the yield-curve hint when it is more severe than rate-cut", () => {
    const rows = buildSignalRows({
      ...emptySignals,
      us_rate_curve: {
        yield_curve_value: -0.6,
        yield_curve_state: "DEEPLY_INVERTED",
        rate_cut_value: -0.1,
        rate_cut_level: "NEUTRAL",
        date: "2024-01-15",
        sub_score: 3,
      },
    });
    const row = rows.find((r) => r.key === "us_rate_curve")!;
    expect(row.content?.hintText).toBe("침체 위험 높음, 안전자산 비중 점검");
    expect(row.content?.dotColor).toBe("bg-red-500");
  });

  it("picks the rate-cut hint when it is more severe than yield-curve", () => {
    const rows = buildSignalRows({
      ...emptySignals,
      us_rate_curve: {
        yield_curve_value: 0.6,
        yield_curve_state: "POSITIVE",
        rate_cut_value: -1.6,
        rate_cut_level: "DEEP_CUT_EXPECTED",
        date: "2024-01-15",
        sub_score: 3,
      },
    });
    const row = rows.find((r) => r.key === "us_rate_curve")!;
    expect(row.content?.hintText).toBe("경기둔화 우려, 장기채·성장주 비중 점검");
  });

  it("picks the more severe of CPI/PCE for the merged inflation hint", () => {
    const rows = buildSignalRows({
      ...emptySignals,
      inflation: {
        cpi_yoy_pct: 5.0,
        cpi_level: "BREAKOUT",
        pce_yoy_pct: 2.5,
        pce_level: "ELEVATED",
        date: "2024-01-15",
        sub_score: 3,
      },
    });
    const row = rows.find((r) => r.key === "inflation")!;
    expect(row.content?.hintText).toBe("목표 큰폭 상회, 금리인상 재개 리스크");
  });

  it("formats a simple single-level signal (vix)", () => {
    const rows = buildSignalRows({
      ...emptySignals,
      vix: { value: 20.5, level: "MEDIUM", date: "2024-01-15", sub_score: 1 },
    });
    const row = rows.find((r) => r.key === "vix")!;
    expect(row.content).toEqual({
      dotColor: "bg-yellow-500",
      valueText: "20.5 · 보통",
      hintText: "모니터링",
      subScore: 1,
    });
  });
});
