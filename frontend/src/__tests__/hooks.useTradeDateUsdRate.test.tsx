import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTradeDateUsdRate } from "@/hooks/useTradeDateUsdRate";
import { fetchUsdKrwOn } from "@/api/assets";

vi.mock("../api/assets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/assets")>()),
  fetchUsdKrwOn: vi.fn(),
}));

// 모달을 닫았다 다시 여는 것처럼 같은 QueryClient에서 훅을 두 번 마운트한다
async function mountTwice() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  for (let i = 0; i < 2; i++) {
    const { result, unmount } = renderHook(() => useTradeDateUsdRate("2026-05-09", true, 1400), {
      wrapper,
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    unmount();
  }
}

describe("useTradeDateUsdRate 캐시", () => {
  beforeEach(() => vi.mocked(fetchUsdKrwOn).mockReset());

  it("못 받은 결과(null)는 다시 마운트하면 재조회한다 (plans/157 B1)", async () => {
    vi.mocked(fetchUsdKrwOn).mockResolvedValue({ usd_krw: null, rate_date: null });
    await mountTwice();
    expect(vi.mocked(fetchUsdKrwOn)).toHaveBeenCalledTimes(2);
  });

  it("받은 종가는 다시 묻지 않는다", async () => {
    vi.mocked(fetchUsdKrwOn).mockResolvedValue({ usd_krw: 1300, rate_date: "2026-05-08" });
    await mountTwice();
    expect(vi.mocked(fetchUsdKrwOn)).toHaveBeenCalledTimes(1);
  });
});
