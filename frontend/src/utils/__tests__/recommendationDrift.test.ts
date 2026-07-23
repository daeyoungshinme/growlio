import { describe, it, expect } from "vitest";
import {
  buildWeightDiffRows,
  computeRecommendationDrift,
  hasSignificantDrift,
  RECOMMENDATION_DRIFT_THRESHOLD_PCT,
} from "@/utils/recommendationDrift";
import type { GoalRecommendationItem } from "@/api/rebalancing";
import type { PortfolioItem } from "@/api/portfolios";

const recItem = (overrides: Partial<GoalRecommendationItem> = {}): GoalRecommendationItem => ({
  ticker: "AAPL",
  name: "Apple Inc.",
  market: "NASDAQ",
  weight: 50,
  ...overrides,
});

const portItem = (overrides: Partial<PortfolioItem> = {}): PortfolioItem => ({
  ticker: "AAPL",
  name: "Apple Inc.",
  market: "NASDAQ",
  weight: 50,
  ...overrides,
});

describe("computeRecommendationDrift", () => {
  it("returns zero drift when recommendation matches current weights exactly", () => {
    const result = computeRecommendationDrift(
      [recItem({ weight: 50 })],
      [portItem({ weight: 50 })],
    );
    expect(result).toEqual({ maxDeltaPct: 0, newCandidateCount: 0 });
  });

  it("computes the max absolute delta among matched tickers", () => {
    const result = computeRecommendationDrift(
      [
        recItem({ ticker: "AAPL", weight: 60 }),
        recItem({ ticker: "MSFT", weight: 40, name: "Microsoft" }),
      ],
      [
        portItem({ ticker: "AAPL", weight: 50 }),
        portItem({ ticker: "MSFT", weight: 50, name: "Microsoft" }),
      ],
    );
    expect(result.maxDeltaPct).toBe(10);
    expect(result.newCandidateCount).toBe(0);
  });

  it("counts recommended tickers absent from the current portfolio as new candidates", () => {
    const result = computeRecommendationDrift(
      [
        recItem({ ticker: "AAPL", weight: 50 }),
        recItem({ ticker: "GOOG", weight: 50, name: "Alphabet" }),
      ],
      [portItem({ ticker: "AAPL", weight: 50 })],
    );
    expect(result.newCandidateCount).toBe(1);
    expect(result.maxDeltaPct).toBe(0);
  });

  it("matches items by ticker+market pair, not ticker alone", () => {
    const result = computeRecommendationDrift(
      [recItem({ ticker: "AAPL", market: "NASDAQ", weight: 50 })],
      [portItem({ ticker: "AAPL", market: "KOSPI", weight: 50 })],
    );
    expect(result.newCandidateCount).toBe(1);
  });

  it("rounds maxDeltaPct to one decimal place", () => {
    const result = computeRecommendationDrift(
      [recItem({ weight: 33.33 })],
      [portItem({ weight: 30 })],
    );
    expect(result.maxDeltaPct).toBe(3.3);
  });

  it("returns zero drift for empty recommendation list", () => {
    const result = computeRecommendationDrift([], [portItem()]);
    expect(result).toEqual({ maxDeltaPct: 0, newCandidateCount: 0 });
  });
});

describe("hasSignificantDrift", () => {
  it("is false below the threshold with no new candidates", () => {
    expect(
      hasSignificantDrift({
        maxDeltaPct: RECOMMENDATION_DRIFT_THRESHOLD_PCT - 0.1,
        newCandidateCount: 0,
      }),
    ).toBe(false);
  });

  it("is true at or above the threshold", () => {
    expect(
      hasSignificantDrift({
        maxDeltaPct: RECOMMENDATION_DRIFT_THRESHOLD_PCT,
        newCandidateCount: 0,
      }),
    ).toBe(true);
  });

  it("is true whenever there is at least one new candidate, regardless of delta", () => {
    expect(hasSignificantDrift({ maxDeltaPct: 0, newCandidateCount: 1 })).toBe(true);
  });
});

describe("buildWeightDiffRows", () => {
  it("merges a matched ticker into a single row with both weights", () => {
    const rows = buildWeightDiffRows(
      [recItem({ ticker: "AAPL", weight: 60 })],
      [portItem({ ticker: "AAPL", weight: 40 })],
    );
    expect(rows).toEqual([
      {
        key: "AAPL-NASDAQ",
        name: "Apple Inc.",
        ticker: "AAPL",
        market: "NASDAQ",
        currentWeight: 40,
        recommendedWeight: 60,
      },
    ]);
  });

  it("marks a recommended-only ticker with currentWeight null", () => {
    const rows = buildWeightDiffRows(
      [recItem({ ticker: "GOOG", name: "Alphabet", weight: 30 })],
      [portItem({ ticker: "AAPL", weight: 100 })],
    );
    const goog = rows.find((r) => r.ticker === "GOOG");
    expect(goog).toMatchObject({ currentWeight: null, recommendedWeight: 30 });
    const aapl = rows.find((r) => r.ticker === "AAPL");
    expect(aapl).toMatchObject({ currentWeight: 100, recommendedWeight: null });
  });

  it("sorts rows by recommended weight descending", () => {
    const rows = buildWeightDiffRows(
      [
        recItem({ ticker: "AAPL", weight: 20 }),
        recItem({ ticker: "MSFT", name: "Microsoft", weight: 80 }),
      ],
      [],
    );
    expect(rows.map((r) => r.ticker)).toEqual(["MSFT", "AAPL"]);
  });

  it("returns an empty array when both lists are empty", () => {
    expect(buildWeightDiffRows([], [])).toEqual([]);
  });
});
