import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setupPreloadErrorReload } from "@/lib/serviceWorker";

describe("setupPreloadErrorReload", () => {
  const reload = vi.fn();
  const originalLocation = window.location;

  beforeEach(() => {
    sessionStorage.clear();
    reload.mockReset();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...originalLocation, reload },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", { configurable: true, value: originalLocation });
    vi.useRealTimers();
  });

  function firePreloadError(): Event {
    const event = new Event("vite:preloadError", { cancelable: true });
    window.dispatchEvent(event);
    return event;
  }

  it("배포로 사라진 청크면 한 번 새로고침한다", () => {
    setupPreloadErrorReload();
    const event = firePreloadError();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("1분 안에 또 나면 새로고침하지 않아 무한 루프를 막는다", () => {
    vi.useFakeTimers();
    setupPreloadErrorReload();
    firePreloadError();
    vi.advanceTimersByTime(30_000);
    const second = firePreloadError();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(second.defaultPrevented).toBe(false);
  });
});
