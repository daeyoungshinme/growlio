import { useCallback, useEffect, useRef, useState } from "react";
import { triggerHaptic } from "./useHaptic";

interface UsePullToRefreshOptions {
  onRefresh: () => Promise<void>;
  containerRef: React.RefObject<HTMLElement | null>;
  threshold?: number;
  disabled?: boolean;
}

interface UsePullToRefreshResult {
  isPulling: boolean;
  pullDistance: number;
  isRefreshing: boolean;
}

export function usePullToRefresh({
  onRefresh,
  containerRef,
  threshold = 60,
  disabled = false,
}: UsePullToRefreshOptions): UsePullToRefreshResult {
  const [isPulling, setIsPulling] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const startYRef = useRef(0);
  const hapticFiredRef = useRef(false);
  // touchend 핸들러가 최신 값을 ref로 읽어 리스너를 다시 붙이지 않게 한다 — 예전엔 pullDistance가 바뀌는
  // 매 touchmove마다 handleTouchEnd가 새로 만들어져 리스너 3개를 떼고 다시 붙였다
  const pullDistanceRef = useRef(0);
  const isPullingRef = useRef(false);
  const isRefreshingRef = useRef(false);
  const onRefreshRef = useRef(onRefresh);
  useEffect(() => {
    onRefreshRef.current = onRefresh;
  }, [onRefresh]);
  const frameRef = useRef<number | null>(null);

  const setDistance = useCallback((value: number) => {
    pullDistanceRef.current = value;
    // 화면 갱신은 프레임당 한 번 — touchmove는 프레임보다 자주 온다
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      setPullDistance(pullDistanceRef.current);
    });
  }, []);

  const handleTouchStart = useCallback(
    (e: TouchEvent) => {
      const el = containerRef.current;
      const touch = e.touches[0];
      if (disabled || !el || el.scrollTop > 0 || !touch) return;
      startYRef.current = touch.clientY;
      hapticFiredRef.current = false;
    },
    [disabled, containerRef],
  );

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      const el = containerRef.current;
      const touch = e.touches[0];
      if (disabled || !el || el.scrollTop > 0 || !touch) return;

      const delta = touch.clientY - startYRef.current;
      if (delta <= 0) return;

      // 기본 스크롤 방지 (당기는 중일 때만)
      e.preventDefault();

      const clamped = Math.min(delta * 0.5, threshold * 1.5);
      if (!isPullingRef.current) {
        isPullingRef.current = true;
        setIsPulling(true);
      }
      setDistance(clamped);

      if (clamped >= threshold && !hapticFiredRef.current) {
        hapticFiredRef.current = true;
        void triggerHaptic("medium");
      }
    },
    [disabled, containerRef, threshold, setDistance],
  );

  const handleTouchEnd = useCallback(async () => {
    if (!isPullingRef.current) return;
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    const reached = pullDistanceRef.current >= threshold;
    isPullingRef.current = false;
    pullDistanceRef.current = 0;
    setIsPulling(false);
    setPullDistance(0);

    if (reached && !isRefreshingRef.current) {
      isRefreshingRef.current = true;
      setIsRefreshing(true);
      try {
        await onRefreshRef.current();
      } finally {
        isRefreshingRef.current = false;
        setIsRefreshing(false);
      }
    }
  }, [threshold]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchmove", handleTouchMove, { passive: false });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchmove", handleTouchMove);
      el.removeEventListener("touchend", handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchMove, handleTouchEnd, containerRef]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  return { isPulling, pullDistance, isRefreshing };
}
