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

  /** 맨 위에서 시작한 터치면 당김을 준비하고 true — 그때만 non-passive touchmove를 붙인다 */
  const handleTouchStart = useCallback(
    (e: TouchEvent): boolean => {
      const el = containerRef.current;
      const touch = e.touches[0];
      if (disabled || !el || el.scrollTop > 0 || !touch) return false;
      startYRef.current = touch.clientY;
      hapticFiredRef.current = false;
      return true;
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

    // non-passive touchmove는 맨 위에서 시작한 제스처 동안만 붙인다 — 앱의 유일한 스크롤 컨테이너에 항상 붙어 있으면
    // 모든 스크롤이 JS 메인 스레드 응답을 기다려(청크 파싱·쿼리 폭주 중) 저사양 Android에서 버벅였다(plans/125 E2)
    let moveAttached = false;
    const detachMove = () => {
      if (!moveAttached) return;
      el.removeEventListener("touchmove", handleTouchMove);
      moveAttached = false;
    };
    const onStart = (e: TouchEvent) => {
      detachMove();
      if (handleTouchStart(e)) {
        el.addEventListener("touchmove", handleTouchMove, { passive: false });
        moveAttached = true;
      }
    };
    const onEnd = () => {
      detachMove();
      void handleTouchEnd();
    };

    el.addEventListener("touchstart", onStart, { passive: true });
    el.addEventListener("touchend", onEnd, { passive: true });
    el.addEventListener("touchcancel", onEnd, { passive: true });

    return () => {
      detachMove();
      el.removeEventListener("touchstart", onStart);
      el.removeEventListener("touchend", onEnd);
      el.removeEventListener("touchcancel", onEnd);
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
