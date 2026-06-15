import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { ExchangeRateProvider } from "@/context/ExchangeRateContext";

vi.mock("@/api/assets", () => ({
  fetchExchangeRate: vi.fn(),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>
      <ExchangeRateProvider>{children}</ExchangeRateProvider>
    </QueryClientProvider>
  );
}

describe("useExchangeRate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("초기 상태에서 null을 반환한다", () => {
    const { result } = renderHook(() => useExchangeRate(), {
      wrapper: createWrapper(),
    });
    expect(result.current).toBeNull();
  });

  it("API 성공 시 usd_krw 값을 반환한다", async () => {
    const { fetchExchangeRate } = await import("@/api/assets");
    vi.mocked(fetchExchangeRate).mockResolvedValue({ usd_krw: 1350 });

    const { result } = renderHook(() => useExchangeRate(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current).toBe(1350));
  });

  it("API 오류 시 toast 에러 메시지를 표시한다", async () => {
    const { fetchExchangeRate } = await import("@/api/assets");
    const { toast } = await import("@/utils/toast");
    vi.mocked(fetchExchangeRate).mockRejectedValue(new Error("네트워크 오류"));

    renderHook(() => useExchangeRate(), {
      wrapper: createWrapper(),
    });

    await waitFor(
      () => expect(vi.mocked(toast)).toHaveBeenCalledWith(
        expect.stringContaining("환율"),
        "error"
      ),
      { timeout: 3000 }
    );
  });

  it("usd_krw가 null이면 null을 반환한다", async () => {
    const { fetchExchangeRate } = await import("@/api/assets");
    vi.mocked(fetchExchangeRate).mockResolvedValue({ usd_krw: 0 });

    const { result } = renderHook(() => useExchangeRate(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current).toBe(0));
  });
});
