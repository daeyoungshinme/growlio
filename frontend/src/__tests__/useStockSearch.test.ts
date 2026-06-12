import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useStockSearch } from "@/hooks/useStockSearch";

vi.mock("@/api/assets", () => ({
  searchStocks: vi.fn(),
}));

vi.mock("@/utils/toast", () => ({
  toast: vi.fn(),
}));

describe("useStockSearch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("초기 상태: suggestions는 빈 배열, isSearching은 false", () => {
    const { result } = renderHook(() => useStockSearch());
    expect(result.current.suggestions).toEqual([]);
    expect(result.current.isSearching).toBe(false);
    expect(result.current.isSearchError).toBe(false);
  });

  it("빈 쿼리 검색 시 suggestions를 초기화한다", async () => {
    const { result } = renderHook(() => useStockSearch(0));

    const { searchStocks } = await import("@/api/assets");
    vi.mocked(searchStocks).mockResolvedValue([
      { ticker: "005930", name: "삼성전자", market: "KOSPI", exchange: "KRX" },
    ]);

    act(() => { result.current.search("삼성"); });
    await waitFor(() => expect(result.current.suggestions).toHaveLength(1));

    act(() => { result.current.search(""); });
    expect(result.current.suggestions).toEqual([]);
    expect(result.current.isSearchError).toBe(false);
  });

  it("공백만 있는 쿼리는 검색을 실행하지 않는다", async () => {
    const { result } = renderHook(() => useStockSearch(0));
    const { searchStocks } = await import("@/api/assets");

    act(() => { result.current.search("   "); });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });

    expect(searchStocks).not.toHaveBeenCalled();
    expect(result.current.suggestions).toEqual([]);
  });

  it("debounce 후 searchStocks를 호출한다", async () => {
    const { result } = renderHook(() => useStockSearch(0));
    const { searchStocks } = await import("@/api/assets");
    const mockSuggestions = [{ ticker: "005930", name: "삼성전자", market: "KOSPI", exchange: "KRX" }];
    vi.mocked(searchStocks).mockResolvedValue(mockSuggestions);

    act(() => { result.current.search("삼성"); });
    await waitFor(() => expect(result.current.suggestions).toEqual(mockSuggestions));
    expect(vi.mocked(searchStocks).mock.calls[0][0]).toBe("삼성");
  });

  it("검색 실패 시 isSearchError가 true가 되고 toast를 호출한다", async () => {
    const { result } = renderHook(() => useStockSearch(0));
    const { searchStocks } = await import("@/api/assets");
    const { toast } = await import("@/utils/toast");
    vi.mocked(searchStocks).mockRejectedValue(new Error("네트워크 오류"));

    act(() => { result.current.search("삼성"); });
    await waitFor(() => expect(result.current.isSearchError).toBe(true));

    expect(toast).toHaveBeenCalledWith("종목 검색에 실패했습니다", "error");
    expect(result.current.suggestions).toEqual([]);
    expect(result.current.isSearching).toBe(false);
  });

  it("clearSuggestions가 suggestions와 오류를 초기화한다", async () => {
    const { result } = renderHook(() => useStockSearch(0));
    const { searchStocks } = await import("@/api/assets");
    vi.mocked(searchStocks).mockResolvedValue([
      { ticker: "005930", name: "삼성전자", market: "KOSPI", exchange: "KRX" },
    ]);

    act(() => { result.current.search("삼성"); });
    await waitFor(() => expect(result.current.suggestions).toHaveLength(1));

    act(() => { result.current.clearSuggestions(); });
    expect(result.current.suggestions).toEqual([]);
    expect(result.current.isSearchError).toBe(false);
  });

  it("이전 검색 타이머를 취소하고 마지막 쿼리만 검색한다", async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useStockSearch(300));
      const { searchStocks } = await import("@/api/assets");
      vi.mocked(searchStocks).mockResolvedValue([]);

      act(() => { result.current.search("삼"); });
      act(() => { result.current.search("삼성"); });
      act(() => { result.current.search("삼성전"); });

      await act(async () => {
        vi.runAllTimers();
        for (let i = 0; i < 5; i++) await Promise.resolve();
      });

      expect(searchStocks).toHaveBeenCalledTimes(1);
      expect(vi.mocked(searchStocks).mock.calls[0][0]).toBe("삼성전");
    } finally {
      vi.useRealTimers();
    }
  });

  it("언마운트 시 진행 중인 요청이 abort된다", async () => {
    const { result, unmount } = renderHook(() => useStockSearch(0));
    const { searchStocks } = await import("@/api/assets");
    let capturedSignal: AbortSignal | undefined;
    vi.mocked(searchStocks).mockImplementation((_, signal) => {
      capturedSignal = signal;
      return new Promise(() => {});
    });

    act(() => { result.current.search("삼성"); });
    await act(async () => { await new Promise((r) => setTimeout(r, 10)); });

    unmount();
    expect(capturedSignal?.aborted).toBe(true);
  });
});
