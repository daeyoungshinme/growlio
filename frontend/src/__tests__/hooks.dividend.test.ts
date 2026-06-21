import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock("@/api/client", () => {
  const mockApi = { get: vi.fn() };
  return { api: mockApi };
});

// ── imports ───────────────────────────────────────────────────────────────────

import { useDividendData } from "@/hooks/useDividendData";
import { api } from "@/api/client";

// ── helpers ───────────────────────────────────────────────────────────────────

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: qc }, children);
}

const mockGet = vi.mocked(api.get);

const MOCK_POSITIONS = [{ ticker: "AAPL", market: "NASDAQ", dividend_yield: 0.005 }];
const MOCK_SUMMARY = {
  annual_received: 100000,
  estimated_annual: 200000,
  monthly_breakdown: [{ month: "2025-01", amount: 10000 }],
  monthly_ticker_breakdown: [{ month: "2025-01", ticker: "AAPL", amount: 10000 }],
};
const MOCK_BY_TICKER = [{ ticker: "AAPL", total_received: 50000, annual_estimate: 100000 }];

// ── tests ─────────────────────────────────────────────────────────────────────

describe("useDividendData", () => {
  beforeEach(() => vi.clearAllMocks());

  it("enabled=true일 때 3개 엔드포인트를 모두 호출하고 데이터를 반환한다", async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === "/dividends/positions") return Promise.resolve({ data: MOCK_POSITIONS });
      if (url === "/dividends/summary") return Promise.resolve({ data: MOCK_SUMMARY });
      return Promise.resolve({ data: MOCK_BY_TICKER });
    });

    const { result } = renderHook(() => useDividendData(true), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.dividendPositions).toEqual(MOCK_POSITIONS);
    expect(result.current.dividendSummary).toEqual(MOCK_SUMMARY);
    expect(result.current.dividendByTicker).toEqual(MOCK_BY_TICKER);
    expect(mockGet).toHaveBeenCalledWith("/dividends/positions");
    expect(mockGet).toHaveBeenCalledWith("/dividends/summary");
    expect(mockGet).toHaveBeenCalledWith("/dividends/by-ticker");
  });

  it("enabled=false일 때 API를 호출하지 않고 기본값을 반환한다", () => {
    const { result } = renderHook(() => useDividendData(false), { wrapper: createWrapper() });

    expect(mockGet).not.toHaveBeenCalled();
    expect(result.current.dividendPositions).toEqual([]);
    expect(result.current.dividendByTicker).toEqual([]);
    expect(result.current.dividendSummary).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.isError).toBe(false);
  });

  it("로딩 중에 isLoading이 true다", () => {
    mockGet.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useDividendData(true), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
  });

  it("첫 번째 쿼리 에러 시 isError가 true다", async () => {
    mockGet.mockRejectedValue(new Error("API Error"));

    const { result } = renderHook(() => useDividendData(true), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
