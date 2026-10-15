import { useCallback, useEffect, useRef } from "react";

/**
 * 언마운트 시 자동 해제되는 setTimeout. 다시 예약하면 이전 예약은 취소된다.
 * "3초 뒤 확인 상태 해제"·blur 후 드롭다운 닫기처럼 상태를 바꾸는 지연 콜백용.
 */
export function useTimeout(): (fn: () => void, ms: number) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  return useCallback((fn: () => void, ms: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      fn();
    }, ms);
  }, []);
}
