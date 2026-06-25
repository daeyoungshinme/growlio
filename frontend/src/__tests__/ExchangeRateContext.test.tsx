import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { ExchangeRateProvider, useExchangeRateContext } from "@/context/ExchangeRateContext";

vi.mock("@/api/assets", () => ({
  fetchExchangeRate: vi.fn().mockResolvedValue({ usd_krw: 1350 }),
  fetchAccounts: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <ExchangeRateProvider>{children}</ExchangeRateProvider>
    </QueryClientProvider>
  );
}

describe("ExchangeRateProvider", () => {
  beforeEach(() => vi.clearAllMocks());

  it("환율을 조회하고 자식에게 rate를 제공한다", async () => {
    const { result } = renderHook(() => useExchangeRateContext(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.rate).toBe(1350));
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("로딩 중 isLoading이 true다", async () => {
    const { fetchExchangeRate } = await import("@/api/assets");
    vi.mocked(fetchExchangeRate).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useExchangeRateContext(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.rate).toBeNull();
  });

  it("API 에러 시 rate=null, error가 설정된다", async () => {
    const { fetchExchangeRate } = await import("@/api/assets");
    vi.mocked(fetchExchangeRate).mockRejectedValueOnce(new Error("network error"));

    const { result } = renderHook(() => useExchangeRateContext(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.rate).toBeNull();
    expect(result.current.error).toBeInstanceOf(Error);
  });
});

describe("useExchangeRateContext — Provider 없는 기본값", () => {
  it("Provider 없이 호출하면 기본값(null, false, null)을 반환한다", () => {
    const { result } = renderHook(() => useExchangeRateContext());

    expect(result.current.rate).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  });
});
