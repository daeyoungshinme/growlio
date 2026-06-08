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

  const handleTouchStart = useCallback(
    (e: TouchEvent) => {
      const el = containerRef.current;
      if (disabled || !el || el.scrollTop > 0) return;
      startYRef.current = e.touches[0].clientY;
      hapticFiredRef.current = false;
    },
    [disabled, containerRef]
  );

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      const el = containerRef.current;
      if (disabled || !el || el.scrollTop > 0) return;

      const delta = e.touches[0].clientY - startYRef.current;
      if (delta <= 0) return;

      // 기본 스크롤 방지 (당기는 중일 때만)
      e.preventDefault();

      const clamped = Math.min(delta * 0.5, threshold * 1.5);
      setIsPulling(true);
      setPullDistance(clamped);

      if (clamped >= threshold && !hapticFiredRef.current) {
        hapticFiredRef.current = true;
        void triggerHaptic("medium");
      }
    },
    [disabled, containerRef, threshold]
  );

  const handleTouchEnd = useCallback(async () => {
    if (!isPulling) return;

    if (pullDistance >= threshold && !isRefreshing) {
      setIsRefreshing(true);
      setPullDistance(0);
      setIsPulling(false);
      try {
        await onRefresh();
      } finally {
        setIsRefreshing(false);
      }
    } else {
      setIsPulling(false);
      setPullDistance(0);
    }
  }, [isPulling, pullDistance, threshold, isRefreshing, onRefresh]);

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

  return { isPulling, pullDistance, isRefreshing };
}
