import { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { triggerHaptic } from "./useHaptic";

const NAV_ORDER = ["/dashboard", "/assets", "/rebalancing", "/invest-plan", "/settings"];

const SWIPE_THRESHOLD = 50; // px
const VELOCITY_THRESHOLD = 0.3; // px/ms
const ANGLE_RATIO = 1.5; // 수평 성분이 수직 성분보다 이 배 이상이어야 탭 전환

interface TouchState {
  startX: number;
  startY: number;
  startTime: number;
}

function useSwipeGesture(
  containerRef: React.RefObject<HTMLElement | null>,
  onSwipe: (deltaX: number, e: TouchEvent) => void,
) {
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

      onSwipe(deltaX, e);
    },
    [onSwipe],
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

/** 하단 네비 5탭(홈/자산/리밸런싱/계획/설정) 간 페이지 전환 스와이프 */
export function useSwipeNavigation(containerRef: React.RefObject<HTMLElement | null>) {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const handleSwipe = useCallback(
    (deltaX: number) => {
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
    [pathname, navigate],
  );

  useSwipeGesture(containerRef, handleSwipe);
}

/** 페이지 내부 하위 탭(예: 종목현황/배당/세금) 간 전환 스와이프 — 상위 페이지 스와이프로 전파되지 않도록 이벤트를 소비함 */
export function useSwipeTabs<T extends string>(
  containerRef: React.RefObject<HTMLElement | null>,
  tabs: readonly T[],
  activeTab: T,
  onChange: (tab: T) => void,
) {
  const handleSwipe = useCallback(
    (deltaX: number, e: TouchEvent) => {
      // 상위 mainRef의 페이지 전환 스와이프와 중복 발동되지 않도록 여기서 소비함
      e.stopPropagation();

      const currentIndex = tabs.indexOf(activeTab);
      if (currentIndex === -1) return;

      if (deltaX < 0 && currentIndex < tabs.length - 1) {
        void triggerHaptic("light");
        onChange(tabs[currentIndex + 1]);
      } else if (deltaX > 0 && currentIndex > 0) {
        void triggerHaptic("light");
        onChange(tabs[currentIndex - 1]);
      }
    },
    [tabs, activeTab, onChange],
  );

  useSwipeGesture(containerRef, handleSwipe);
}
