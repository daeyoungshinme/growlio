import { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { triggerHaptic } from "./useHaptic";

const NAV_ORDER = [
  "/dashboard",
  "/portfolio",
  "/asset-management",
  "/invest-plan",
  "/settings",
];

const SWIPE_THRESHOLD = 50;     // px
const VELOCITY_THRESHOLD = 0.3; // px/ms
const ANGLE_RATIO = 1.5;        // 수평 성분이 수직 성분보다 이 배 이상이어야 탭 전환

interface TouchState {
  startX: number;
  startY: number;
  startTime: number;
}

export function useSwipeNavigation(containerRef: React.RefObject<HTMLElement | null>) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const touchRef = useRef<TouchState | null>(null);

  const handleTouchStart = useCallback((e: TouchEvent) => {
    touchRef.current = {
      startX: e.touches[0].clientX,
      startY: e.touches[0].clientY,
      startTime: performance.now(),
    };
  }, []);

  const handleTouchEnd = useCallback(
    (e: TouchEvent) => {
      const start = touchRef.current;
      if (!start) return;
      touchRef.current = null;

      // 모달이 열려 있으면 스와이프 무시
      if (document.body.style.overflow === "hidden") return;

      const deltaX = e.changedTouches[0].clientX - start.startX;
      const deltaY = e.changedTouches[0].clientY - start.startY;
      const elapsed = performance.now() - start.startTime;
      const velocity = Math.abs(deltaX) / elapsed;

      const isHorizontal = Math.abs(deltaX) > Math.abs(deltaY) * ANGLE_RATIO;
      const isSignificant = Math.abs(deltaX) > SWIPE_THRESHOLD && velocity > VELOCITY_THRESHOLD;

      if (!isHorizontal || !isSignificant) return;

      const currentIndex = NAV_ORDER.findIndex((p) => pathname.startsWith(p));
      if (currentIndex === -1) return;

      if (deltaX < 0 && currentIndex < NAV_ORDER.length - 1) {
        void triggerHaptic("light");
        navigate(NAV_ORDER[currentIndex + 1]);
      } else if (deltaX > 0 && currentIndex > 0) {
        void triggerHaptic("light");
        navigate(NAV_ORDER[currentIndex - 1]);
      }
    },
    [pathname, navigate]
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    el.addEventListener("touchstart", handleTouchStart, { passive: true });
    el.addEventListener("touchend", handleTouchEnd, { passive: true });

    return () => {
      el.removeEventListener("touchstart", handleTouchStart);
      el.removeEventListener("touchend", handleTouchEnd);
    };
  }, [handleTouchStart, handleTouchEnd, containerRef]);
}
