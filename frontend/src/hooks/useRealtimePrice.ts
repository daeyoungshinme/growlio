import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "../lib/supabase";

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

/** WebSocket 재연결 대기시간 (ms) — 지수 백오프 */
const RECONNECT_DELAYS = [1_000, 3_000, 10_000];

function getWsBaseUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const apiDomain = (import.meta.env.VITE_API_DOMAIN as string | undefined) || window.location.host;
  return `${proto}//${apiDomain}`;
}

/**
 * WebSocket 실시간 가격 구독 훅.
 *
 * 백엔드 `/api/v1/ws/prices`에 연결해 30초 간격으로 업데이트를 받는다.
 * tickers 목록이 변경되면 재구독 메시지를 자동 전송한다.
 * 연결 끊김 시 최대 3회 지수 백오프 재연결을 시도한다.
 */
export function useRealtimePrice({
  tickers,
  enabled = true,
  onPrice,
}: UseRealtimePriceOptions) {
  const [prices, setPrices] = useState<Record<string, RealtimePriceData>>({});
  const [connected, setConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const enabledRef = useRef(enabled);
  const tickersRef = useRef(tickers);
  const onPriceRef = useRef(onPrice);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

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

    const url = `${getWsBaseUrl()}/api/v1/ws/prices?token=${encodeURIComponent(session.access_token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectAttemptRef.current = 0;
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
        // eslint-disable-next-line react-hooks/immutability
        void connect();
      }, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [sendSubscribe]);

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, connect]);

  // 종목 목록 변경 시 재구독
  useEffect(() => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      sendSubscribe(ws);
    }
  }, [tickers, sendSubscribe]);

  return { prices, connected };
}
