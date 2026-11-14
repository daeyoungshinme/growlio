import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { syncAccount } from "@/api/assets";
import { invalidateSyncData } from "@/utils/queryInvalidation";
import { useSyncAccounts } from "@/hooks/useSyncAccounts";

vi.mock("@/api/assets", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/assets")>()),
  syncAccount: vi.fn(),
}));
vi.mock("@/utils/queryInvalidation", () => ({ invalidateSyncData: vi.fn() }));

function render() {
  const qc = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(() => useSyncAccounts(), { wrapper }).result;
}

describe("useSyncAccounts (plans/63 P2-3)", () => {
  it("전부 성공하면 done·true, 동기화 쿼리를 무효화한다", async () => {
    vi.mocked(syncAccount).mockResolvedValue({} as never);
    const result = render();
    let ok = false;
    await act(async () => {
      ok = await result.current.run(["a", "b"]);
    });
    expect(ok).toBe(true);
    expect(result.current.state).toBe("done");
    expect(syncAccount).toHaveBeenCalledTimes(2);
    expect(invalidateSyncData).toHaveBeenCalled();
  });

  it("하나라도 실패하면 error·false지만 나머지 결과 반영을 위해 무효화는 한다", async () => {
    vi.mocked(syncAccount).mockReset();
    vi.mocked(invalidateSyncData).mockClear();
    vi.mocked(syncAccount)
      .mockResolvedValueOnce({} as never)
      .mockRejectedValueOnce(new Error("fail"));
    const result = render();
    let ok = true;
    await act(async () => {
      ok = await result.current.run(["a", "b"]);
    });
    expect(ok).toBe(false);
    expect(result.current.state).toBe("error");
    expect(invalidateSyncData).toHaveBeenCalled();
  });

  it("계좌가 없으면 아무것도 하지 않는다", async () => {
    vi.mocked(syncAccount).mockClear();
    const result = render();
    let ok = true;
    await act(async () => {
      ok = await result.current.run([]);
    });
    expect(ok).toBe(false);
    expect(result.current.state).toBe("idle");
    expect(syncAccount).not.toHaveBeenCalled();
  });

  it("한 번에 3개까지만 동기화하고 실패 수를 돌려준다 — plans/128 A2", async () => {
    vi.mocked(syncAccount).mockReset();
    let inFlight = 0;
    let peak = 0;
    vi.mocked(syncAccount).mockImplementation(async (id: string) => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((resolve) => setTimeout(resolve, 5));
      inFlight -= 1;
      if (id === "c") throw new Error("fail");
      return {} as never;
    });
    const result = render();
    let outcome = { total: 0, failed: 0 };
    await act(async () => {
      outcome = await result.current.runWithResult(["a", "b", "c", "d", "e", "f", "g"]);
    });
    expect(outcome).toEqual({ total: 7, failed: 1 });
    expect(syncAccount).toHaveBeenCalledTimes(7);
    expect(peak).toBe(3);
    expect(result.current.state).toBe("error");
  });
});
