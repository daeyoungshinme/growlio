import { describe, it, expect } from "vitest";
import type { CandidateOverlap, OverlapGroup } from "@/api/rebalancing";
import {
  annualCostGapPer10M,
  buildTerMap,
  formatTerPct,
  groupsTouchingItems,
  isMixedListing,
  overlapWarningFor,
  reasonLabel,
  weightedTerPct,
} from "@/utils/etfOverlap";

function member(ticker: string, market: string, held = false) {
  return {
    ticker,
    name: `${ticker} ETF`,
    market,
    held,
    candidate: !held,
    ter_pct: null,
    base_index: null,
  };
}

function group(overrides: Partial<OverlapGroup> = {}): OverlapGroup {
  return {
    reasons: ["SAME_INDEX"],
    max_correlation: null,
    members: [member("A", "NYSE", true), member("B", "NYSE")],
    cheapest_ticker: null,
    cheapest_market: null,
    ter_gap_pct: null,
    ...overrides,
  };
}

describe("etfOverlap utils", () => {
  it("formats tiny and normal fees without collapsing to zero", () => {
    expect(formatTerPct(0.0068)).toBe("0.0068%");
    expect(formatTerPct(0.0945)).toBe("0.0945%");
    expect(formatTerPct(0.45)).toBe("0.45%");
  });

  it("converts a fee gap into annual cost per 10M KRW", () => {
    expect(annualCostGapPer10M(0.09)).toBe(9000);
  });

  it("computes the weighted fee over covered weight only", () => {
    const terMap = buildTerMap({
      groups: [],
      profiles: [
        {
          ticker: "A",
          market: "NYSE",
          ter_pct: 0.1,
          base_index: null,
          issuer: null,
          tracking_error_pct: null,
        },
      ],
      price_data_available: true,
    });
    const result = weightedTerPct(
      [
        { ticker: "A", market: "NYSE", weight: 60 },
        { ticker: "B", market: "NYSE", weight: 40 },
      ],
      terMap,
    );
    expect(result?.pct).toBeCloseTo(0.1);
    expect(result?.coveragePct).toBeCloseTo(60);
    expect(weightedTerPct([{ ticker: "B", market: "NYSE", weight: 100 }], terMap)).toBeNull();
  });

  it("keeps only groups containing a positively weighted item", () => {
    const g = group();
    expect(groupsTouchingItems([g], [{ ticker: "B", market: "NYSE", weight: 10 }])).toEqual([g]);
    expect(groupsTouchingItems([g], [{ ticker: "B", market: "NYSE", weight: 0 }])).toEqual([]);
  });

  it("detects mixed domestic/overseas listings", () => {
    expect(isMixedListing(group())).toBe(false);
    expect(
      isMixedListing(group({ members: [member("A", "NYSE"), member("360750", "KOSPI")] })),
    ).toBe(true);
  });

  it("labels reasons with correlation", () => {
    expect(
      reasonLabel(group({ reasons: ["SAME_INDEX", "HIGH_CORR"], max_correlation: 0.991 })),
    ).toBe("같은 지수 · 움직임 유사 0.99");
  });

  it("builds a chip warning preferring held members", () => {
    const overlap: CandidateOverlap = {
      groups: [
        group({
          members: [member("B", "NYSE"), member("C", "NYSE"), member("A", "NYSE", true)],
        }),
      ],
      profiles: [],
      price_data_available: true,
    };
    expect(overlapWarningFor(overlap, "B", "NYSE")).toBe("보유 중인 A ETF 외 1개와(과) 같은 지수");
    expect(overlapWarningFor(overlap, "Z", "NYSE")).toBeNull();
    expect(overlapWarningFor(undefined, "B", "NYSE")).toBeNull();
  });
});
