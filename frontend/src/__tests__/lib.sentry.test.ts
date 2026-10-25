import { describe, it, expect, vi, afterEach } from "vitest";

const init = vi.fn();
const capture = vi.fn();
vi.mock("@sentry/react", () => ({
  init,
  captureException: capture,
  browserTracingIntegration: () => ({ name: "BrowserTracing" }),
}));

async function loadModule(dsn: string) {
  vi.resetModules();
  vi.stubEnv("VITE_SENTRY_DSN", dsn);
  return import("@/lib/sentry");
}

describe("lib/sentry 지연 초기화", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    init.mockClear();
    capture.mockClear();
  });

  it("init 전에 잡은 오류는 버퍼링했다가 init 후 전달한다", async () => {
    vi.useFakeTimers();
    const ric = window.requestIdleCallback;
    // @ts-expect-error — jsdom에 없을 수 있음, setTimeout 폴백 경로를 쓴다
    window.requestIdleCallback = undefined;
    const sentry = await loadModule("https://key@example.ingest.sentry.io/1");

    sentry.initSentryDeferred();
    sentry.captureException(new Error("early"));
    expect(init).not.toHaveBeenCalled();

    await vi.runAllTimersAsync();
    vi.useRealTimers();
    await vi.waitFor(() => expect(init).toHaveBeenCalledTimes(1));
    expect(capture).toHaveBeenCalledWith(expect.objectContaining({ message: "early" }), undefined);
    window.requestIdleCallback = ric;
  });

  it("DSN이 없으면 아무것도 로드하지 않는다", async () => {
    const sentry = await loadModule("");
    sentry.initSentryDeferred();
    sentry.captureException(new Error("x"));
    await new Promise((r) => setTimeout(r, 0));
    expect(init).not.toHaveBeenCalled();
    expect(capture).not.toHaveBeenCalled();
  });
});
