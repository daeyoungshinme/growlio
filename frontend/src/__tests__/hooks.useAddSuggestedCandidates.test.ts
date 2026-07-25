import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import type { SuggestedGoalCandidate } from "@/api/rebalancing";
import type { GoalCandidateTicker } from "@/api/settings";

const updateGoalCandidateTickers = vi.fn();
const toastMock = vi.fn();

vi.mock("@/api/settings", () => ({
  updateGoalCandidateTickers: (...args: unknown[]) => updateGoalCandidateTickers(...args),
}));
vi.mock("@/utils/toast", () => ({ toast: (...args: unknown[]) => toastMock(...args) }));

import { useAddSuggestedCandidates } from "@/hooks/useAddSuggestedCandidates";

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const SUGGESTED: SuggestedGoalCandidate[] = [
  {
    ticker: "JEPQ",
    name: "JPMorgan Nasdaq Equity Premium Income ETF",
    market: "NASDAQ",
    asset_class: "EQUITY",
    dividend_yield_pct: 9.95,
  },
];

describe("useAddSuggestedCandidates", () => {
  beforeEach(() => vi.clearAllMocks());

  it("기존 후보 목록에 제안된 후보를 병합해 저장한다", async () => {
    const current: GoalCandidateTicker[] = [
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", asset_class: "EQUITY" },
    ];
    updateGoalCandidateTickers.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAddSuggestedCandidates(current), {
      wrapper: createWrapper(),
    });

    act(() => result.current.mutate(SUGGESTED));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(updateGoalCandidateTickers).toHaveBeenCalledWith([
      { ticker: "SPY", name: "SPDR S&P 500 ETF", market: "NYSE", asset_class: "EQUITY" },
      {
        ticker: "JEPQ",
        name: "JPMorgan Nasdaq Equity Premium Income ETF",
        market: "NASDAQ",
        asset_class: "EQUITY",
      },
    ]);
    expect(toastMock).toHaveBeenCalledWith(expect.stringContaining("추가"), "success");
  });

  it("이미 등록된 종목(ticker+market 일치)은 중복 추가하지 않는다", async () => {
    const current: GoalCandidateTicker[] = [
      {
        ticker: "JEPQ",
        name: "JPMorgan Nasdaq Equity Premium Income ETF",
        market: "NASDAQ",
        asset_class: "EQUITY",
      },
    ];
    updateGoalCandidateTickers.mockResolvedValue(undefined);

    const { result } = renderHook(() => useAddSuggestedCandidates(current), {
      wrapper: createWrapper(),
    });

    act(() => result.current.mutate(SUGGESTED));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(updateGoalCandidateTickers).toHaveBeenCalledWith(current);
  });

  it("저장 실패 시 에러 토스트를 띄운다", async () => {
    updateGoalCandidateTickers.mockRejectedValue(new Error("network error"));

    const { result } = renderHook(() => useAddSuggestedCandidates([]), {
      wrapper: createWrapper(),
    });

    act(() => result.current.mutate(SUGGESTED));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(toastMock).toHaveBeenCalledWith(expect.any(String), "error");
  });
});
