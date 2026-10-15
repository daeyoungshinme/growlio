import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useTimeout } from "@/hooks/useTimeout";

describe("useTimeout", () => {
  it("언마운트하면 예약된 콜백이 실행되지 않는다", () => {
    vi.useFakeTimers();
    const fn = vi.fn();
    const { result, unmount } = renderHook(() => useTimeout());

    result.current(fn, 3000);
    unmount();
    vi.advanceTimersByTime(3000);

    expect(fn).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("다시 예약하면 이전 예약은 취소된다", () => {
    vi.useFakeTimers();
    const first = vi.fn();
    const second = vi.fn();
    const { result } = renderHook(() => useTimeout());

    result.current(first, 3000);
    vi.advanceTimersByTime(2000);
    result.current(second, 3000);
    vi.advanceTimersByTime(3000);

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
    vi.useRealTimers();
  });
});
