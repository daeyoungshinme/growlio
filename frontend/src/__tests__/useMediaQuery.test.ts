import { describe, it, expect, vi, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIsSmUp, useMediaQuery } from "@/hooks/useMediaQuery";

function installMatchMedia(initial: boolean) {
  let matches = initial;
  const listeners = new Set<() => void>();
  const mql = {
    get matches() {
      return matches;
    },
    addEventListener: vi.fn((_: string, cb: () => void) => listeners.add(cb)),
    removeEventListener: vi.fn((_: string, cb: () => void) => listeners.delete(cb)),
  };
  const matchMedia = vi.fn(() => mql);
  vi.stubGlobal("matchMedia", matchMedia);
  return {
    matchMedia,
    mql,
    set(next: boolean) {
      matches = next;
      listeners.forEach((cb) => cb());
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useMediaQuery", () => {
  it("matchMedia가 없으면 null — 호출부가 CSS에 맡긴다", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    expect(result.current).toBeNull();
  });

  it("일치 여부를 반환하고 change 이벤트에 따라 갱신한다", () => {
    const mm = installMatchMedia(false);
    const { result } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    expect(result.current).toBe(false);
    act(() => mm.set(true));
    expect(result.current).toBe(true);
  });

  it("언마운트 시 리스너를 해제한다", () => {
    const mm = installMatchMedia(true);
    const { unmount } = renderHook(() => useMediaQuery("(min-width: 640px)"));
    unmount();
    expect(mm.mql.removeEventListener).toHaveBeenCalled();
  });

  it("useIsSmUp은 sm(640px) 쿼리를 쓴다", () => {
    const mm = installMatchMedia(true);
    const { result } = renderHook(() => useIsSmUp());
    expect(result.current).toBe(true);
    expect(mm.matchMedia).toHaveBeenCalledWith("(min-width: 640px)");
  });
});
