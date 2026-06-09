import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useRealtimePrice } from "../hooks/useRealtimePrice";

vi.mock("../lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({
        data: { session: { access_token: "test-token" } },
      }),
    },
  },
}));

vi.mock("../utils/platform", () => ({
  isNativePlatform: () => false,
}));

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  readyState = 0; // CONNECTING
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = 3;
    this.onclose?.();
  });

  simulateOpen() {
    this.readyState = 1;
    this.onopen?.();
  }

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose() {
    this.readyState = 3;
    this.onclose?.();
  }
}

/** 대기 중인 마이크로태스크를 소진한다 (fake timer 환경 호환). */
const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve();
};

const originalWebSocket = global.WebSocket;

describe("useRealtimePrice", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    // @ts-expect-error — WebSocket mock
    global.WebSocket = MockWebSocket;
    Object.defineProperty(global.WebSocket, "CONNECTING", { value: 0, configurable: true });
    Object.defineProperty(global.WebSocket, "OPEN",       { value: 1, configurable: true });
    Object.defineProperty(global.WebSocket, "CLOSING",    { value: 2, configurable: true });
    Object.defineProperty(global.WebSocket, "CLOSED",     { value: 3, configurable: true });
  });

  afterEach(() => {
    global.WebSocket = originalWebSocket;
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("초기 상태에서 prices는 빈 객체, connected는 false다", () => {
    const { result } = renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: true }),
    );
    expect(result.current.prices).toEqual({});
    expect(result.current.connected).toBe(false);
  });

  it("enabled=false이면 WebSocket을 생성하지 않는다", async () => {
    renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: false }),
    );
    await act(flush);
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("tickers가 빈 배열이면 WebSocket을 생성하지 않는다", async () => {
    renderHook(() => useRealtimePrice({ tickers: [], enabled: true }));
    await act(flush);
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it("WebSocket 연결 성공 시 auth 메시지를 전송한다", async () => {
    renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: true }),
    );
    await act(flush);

    expect(MockWebSocket.instances.length).toBeGreaterThan(0);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    expect(ws.send).toHaveBeenCalledWith(expect.stringContaining('"type":"auth"'));
  });

  it("'connected' 메시지 수신 시 connected 상태가 true가 된다", async () => {
    const { result } = renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: true }),
    );
    await act(flush);

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() => ws.simulateMessage({ type: "connected" }));

    expect(result.current.connected).toBe(true);
  });

  it("price_update 메시지 수신 시 prices 상태가 업데이트된다", async () => {
    const { result } = renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: true }),
    );
    await act(flush);

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() =>
      ws.simulateMessage({
        type: "price_update",
        prices: { "005930": { price: 75_000, market: "KOSPI", updated_at: "2026-01-01T00:00:00Z" } },
      }),
    );

    expect(result.current.prices["005930"]).toEqual({
      price: 75_000,
      market: "KOSPI",
      updated_at: "2026-01-01T00:00:00Z",
    });
  });

  it("WebSocket 연결 종료 시 재연결 타이머를 예약한다", async () => {
    vi.useFakeTimers();

    renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: true }),
    );
    // fake timer 환경에서 microtask 소진
    await act(flush);

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() => ws.simulateClose());

    // 재연결 딜레이(1000ms) 경과
    await act(async () => {
      vi.advanceTimersByTime(1500);
      await flush();
    });

    // 재연결 시도로 새 WebSocket 인스턴스가 생성됨
    expect(MockWebSocket.instances.length).toBeGreaterThan(1);
  }, 10_000);

  it("onPrice 콜백이 price_update 시 호출된다", async () => {
    const onPrice = vi.fn();
    renderHook(() =>
      useRealtimePrice({
        tickers: [{ ticker: "005930", market: "KOSPI" }],
        enabled: true,
        onPrice,
      }),
    );
    await act(flush);

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() =>
      ws.simulateMessage({
        type: "price_update",
        prices: { "005930": { price: 75_000, market: "KOSPI", updated_at: "2026-01-01T00:00:00Z" } },
      }),
    );

    expect(onPrice).toHaveBeenCalledWith("005930", {
      price: 75_000,
      market: "KOSPI",
      updated_at: "2026-01-01T00:00:00Z",
    });
  });

  it("언마운트 시 WebSocket이 닫힌다", async () => {
    const { unmount } = renderHook(() =>
      useRealtimePrice({ tickers: [{ ticker: "005930", market: "KOSPI" }], enabled: true }),
    );
    await act(flush);

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    unmount();

    expect(ws.close).toHaveBeenCalled();
  });

  it("tickers 내용 변경 시 subscribe 메시지를 재전송한다", async () => {
    let tickers = [{ ticker: "005930", market: "KOSPI" }];
    const { rerender } = renderHook(() =>
      useRealtimePrice({ tickers, enabled: true }),
    );
    await act(flush);

    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    const callsBefore = ws.send.mock.calls.length;

    tickers = [{ ticker: "005930", market: "KOSPI" }, { ticker: "000660", market: "KOSPI" }];
    rerender();

    await waitFor(() => expect(ws.send.mock.calls.length).toBeGreaterThan(callsBefore));
    const lastCall = ws.send.mock.calls[ws.send.mock.calls.length - 1][0] as string;
    expect(lastCall).toContain("subscribe");
    expect(lastCall).toContain("000660");
  });
});
