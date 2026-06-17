import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { supabase } from "@/lib/supabase";
import { isNativePlatform } from "@/utils/platform";

export interface TickerInfo {
  ticker: string;
  market: string;
}

export interface RealtimePriceData {
  price: number;
  market: string;
  updated_at: string;
}

interface UseRealtimePriceOptions {
  tickers: TickerInfo[];
  enabled?: boolean;
  onPrice?: (ticker: string, data: RealtimePriceData) => void;
}

/** WebSocket 재연결 대기시간 (ms) — 최대 3회 지수 백오프(1s/3s/10s) */
const RECONNECT_DELAYS = [1_000, 3_000, 10_000];

function getWsBaseUrl(): string {
  if (isNativePlatform()) {
    const domain =
      (import.meta.env.VITE_API_DOMAIN as string | undefined) ?? "growlio-api.onrender.com";
    return `wss://${domain}`;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

/**
 * WebSocket 실시간 가격 구독 훅.
 *
 * 백엔드 `/api/v1/ws/prices`에 연결해 30초 간격으로 업데이트를 받는다.
 * tickers 목록이 변경되면 재구독 메시지를 자동 전송한다.
 * 연결 끊김 시 최대 3회 지수 백오프 재연결을 시도한다.
 */
export function useRealtimePrice({ tickers, enabled = true, onPrice }: UseRealtimePriceOptions) {
  const [prices, setPrices] = useState<Record<string, RealtimePriceData>>({});
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const enabledRef = useRef(enabled);
  const tickersRef = useRef(tickers);
  const onPriceRef = useRef(onPrice);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  // 이전 tickers 내용 추적 — 배열 참조만 바뀐 경우 재구독 방지
  const tickersKeyRef = useRef<string>("");
  const connectRef = useRef<(() => Promise<void>) | null>(null);

  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);
  useEffect(() => {
    tickersRef.current = tickers;
  }, [tickers]);
  useEffect(() => {
    onPriceRef.current = onPrice;
  }, [onPrice]);

  const sendSubscribe = useCallback((ws: WebSocket) => {
    if (tickersRef.current.length === 0) return;
    ws.send(JSON.stringify({ action: "subscribe", tickers: tickersRef.current }));
  }, []);

  const connect = useCallback(async () => {
    if (!mountedRef.current || !enabledRef.current || tickersRef.current.length === 0) return;

    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token || !mountedRef.current) return;

    const url = `${getWsBaseUrl()}/api/v1/ws/prices`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    const token = session.access_token;
    ws.onopen = () => {
      reconnectAttemptRef.current = 0;
      // 토큰을 URL이 아닌 첫 번째 메시지로 전달 (로그/히스토리 노출 방지)
      ws.send(JSON.stringify({ type: "auth", token }));
      sendSubscribe(ws);
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(event.data) as {
          type: string;
          prices?: Record<string, RealtimePriceData>;
        };
        if (msg.type === "connected") {
          setConnected(true);
        } else if (msg.type === "price_update" && msg.prices) {
          setPrices((prev) => ({ ...prev, ...msg.prices }));
          if (onPriceRef.current) {
            for (const [ticker, data] of Object.entries(msg.prices)) {
              onPriceRef.current(ticker, data);
            }
          }
        }
      } catch {
        // JSON 파싱 오류 무시
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (!mountedRef.current || !enabledRef.current) return;
      const delay =
        RECONNECT_DELAYS[Math.min(reconnectAttemptRef.current, RECONNECT_DELAYS.length - 1)];
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        void connectRef.current?.();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [sendSubscribe]);

  useLayoutEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  // 연결 수명주기 관리
  useEffect(() => {
    mountedRef.current = true;
    if (!enabled || tickers.length === 0) return;
    void connect();
    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
    // connect는 sendSubscribe에 의존 — 전체 dep 추가 시 tickers 변경마다 재연결 루프 발생.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, connect]);

  // 앱 포그라운드 복귀 시 즉시 재연결 (Android 백그라운드 전환 대응)
  useEffect(() => {
    const handleVisible = () => {
      if (!enabledRef.current || tickersRef.current.length === 0) return;
      reconnectAttemptRef.current = 0;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const ws = wsRef.current;
      if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
        void connect();
      }
    };

    const handleHidden = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      wsRef.current?.close();
    };

    const onVisibilityChange = () => {
      if (document.hidden) handleHidden();
      else handleVisible();
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [connect]);

  // 종목 목록 내용 변경 시에만 재구독 (배열 참조 변경은 무시)
  useEffect(() => {
    const key = JSON.stringify(tickers);
    if (key === tickersKeyRef.current) return;
    tickersKeyRef.current = key;
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      sendSubscribe(ws);
    }
  }, [tickers, sendSubscribe]);

  return { prices, connected };
}
