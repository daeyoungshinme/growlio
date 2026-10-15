import { describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useStockSearch } from "@/hooks/useStockSearch";
import { searchStocks } from "@/api/assets";

vi.mock("@/api/assets", () => ({ searchStocks: vi.fn() }));
vi.mock("@/utils/toast", () => ({ toast: vi.fn() }));

describe("useStockSearch 중단된 이전 검색", () => {
  it("새 검색이 진행 중이면 이전 요청의 중단이 스피너·결과를 건드리지 않는다", async () => {
    vi.useFakeTimers();
    let resolveSecond!: (v: never[]) => void;
    vi.mocked(searchStocks)
      .mockImplementationOnce(
        (_q, signal) =>
          new Promise((_, reject) =>
            signal?.addEventListener("abort", () => reject(new Error("aborted"))),
          ),
      )
      .mockImplementationOnce(() => new Promise((r) => (resolveSecond = r as never)));
    const { result } = renderHook(() => useStockSearch(10));

    act(() => result.current.search("삼성"));
    await act(async () => vi.advanceTimersByTime(10));
    act(() => result.current.search("삼성전"));
    await act(async () => vi.advanceTimersByTime(10));

    expect(result.current.isSearching).toBe(true);
    await act(async () => resolveSecond([]));
    expect(result.current.isSearching).toBe(false);
    vi.useRealTimers();
  });
});
