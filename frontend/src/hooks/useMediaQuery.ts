import { useCallback, useSyncExternalStore } from "react";

/**
 * CSS 미디어 쿼리 일치 여부. matchMedia가 없는 환경(jsdom 테스트 등)에선 null — 호출부는 null이면
 * 양쪽을 다 렌더하고 CSS(`sm:hidden`/`hidden sm:block`)에 맡긴다.
 */
export function useMediaQuery(query: string): boolean | null {
  const subscribe = useCallback(
    (onChange: () => void) => {
      if (typeof window.matchMedia !== "function") return () => {};
      const mql = window.matchMedia(query);
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : null),
    () => null,
  );
}

/** Tailwind `sm` 이상(640px+) — 모바일 카드 뷰/데스크톱 표 중 실제로 보이는 쪽만 렌더할 때 */
export function useIsSmUp(): boolean | null {
  return useMediaQuery("(min-width: 640px)");
}
