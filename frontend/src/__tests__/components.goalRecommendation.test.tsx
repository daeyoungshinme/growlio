import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { GoalRecommendation } from "@/api/rebalancing";

const fetchGoalRecommendation = vi.fn();

vi.mock("@/api/rebalancing", () => ({
  fetchGoalRecommendation: (...args: unknown[]) => fetchGoalRecommendation(...args),
}));

import GoalRecommendationCard from "@/components/rebalancing/GoalRecommendationCard";
import { usePendingRecommendationStore } from "@/stores/pendingRecommendationStore";

function makeRecommendation(overrides: Partial<GoalRecommendation> = {}): GoalRecommendation {
  return {
    generated_at: "2026-07-06T00:00:00Z",
    is_configured: true,
    required_return_pct: 8.5,
    required_dividend_yield_pct: null,
    recommended_items: [
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 60 },
      { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 40 },
    ],
    expected_return_pct: 9.1,
    expected_dividend_yield_pct: 2.1,
    note: null,
    ...overrides,
  };
}

describe("GoalRecommendationCard", () => {
  beforeEach(() => {
    fetchGoalRecommendation.mockReset();
    usePendingRecommendationStore.getState().clearPending();
  });

  it("renders nothing while not configured", async () => {
    fetchGoalRecommendation.mockResolvedValue(
      makeRecommendation({ is_configured: false, recommended_items: [] }),
    );
    const { container } = renderWithProviders(<GoalRecommendationCard portfolioId="p1" />);
    await waitFor(() => expect(fetchGoalRecommendation).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("renders nothing when there are no recommended items", async () => {
    fetchGoalRecommendation.mockResolvedValue(
      makeRecommendation({ recommended_items: [], note: "이미 목표 금액을 달성했습니다" }),
    );
    const { container } = renderWithProviders(<GoalRecommendationCard portfolioId="p1" />);
    await waitFor(() => expect(fetchGoalRecommendation).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("renders recommended items and required/expected return", async () => {
    fetchGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<GoalRecommendationCard portfolioId="p1" />);

    expect(await screen.findByText("목표 달성 추천 비중")).toBeDefined();
    expect(screen.getByText(/SPY/)).toBeDefined();
    expect(screen.getByText("60.0%")).toBeDefined();
    expect(screen.getByText("40.0%")).toBeDefined();
  });

  it("sets pending recommendation in store when apply is clicked", async () => {
    fetchGoalRecommendation.mockResolvedValue(makeRecommendation());
    renderWithProviders(<GoalRecommendationCard portfolioId="p1" />);

    const applyButton = await screen.findByText("편집기에 적용");
    fireEvent.click(applyButton);

    expect(usePendingRecommendationStore.getState().pending).toEqual({
      portfolioId: "p1",
      items: [
        { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", weight: 60 },
        { ticker: "SCHD", name: "Schwab US Dividend Equity ETF", market: "NYSE", weight: 40 },
      ],
    });
  });
});

describe("usePendingRecommendationStore", () => {
  it("sets and clears pending state", () => {
    const { setPending, clearPending } = usePendingRecommendationStore.getState();
    setPending("p1", [{ ticker: "SPY", name: "SPY", market: "NYSE", weight: 100 }]);
    expect(usePendingRecommendationStore.getState().pending?.portfolioId).toBe("p1");

    clearPending();
    expect(usePendingRecommendationStore.getState().pending).toBeNull();
  });
});
