import { useCallback, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { NAV_ORDER } from "@/constants/nav";
import { triggerHaptic } from "./useHaptic";

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
    const touch = e.touches[0];
    if (!touch) return;
    touchRef.current = {
      startX: touch.clientX,
      startY: touch.clientY,
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

      const touch = e.changedTouches[0];
      if (!touch) return;
      const deltaX = touch.clientX - start.startX;
      const deltaY = touch.clientY - start.startY;
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

      // 범위 밖 인덱스는 undefined — 첫/마지막 탭에서는 넘어가지 않는다
      const target =
        deltaX < 0
          ? NAV_ORDER[currentIndex + 1]
          : deltaX > 0
            ? NAV_ORDER[currentIndex - 1]
            : undefined;
      if (target === undefined) return;
      void triggerHaptic("light");
      void navigate(target);
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

      const target =
        deltaX < 0 ? tabs[currentIndex + 1] : deltaX > 0 ? tabs[currentIndex - 1] : undefined;
      if (target === undefined) return;
      void triggerHaptic("light");
      onChange(target);
    },
    [tabs, activeTab, onChange],
  );

  useSwipeGesture(containerRef, handleSwipe);
}
