import { useCallback, useEffect, useState } from "react";

/**
 * 요소가 화면 근처에 처음 들어왔는지(한 번 true면 유지). 무거운 차트(recharts 청크)를 스크롤해 닿을 때만 마운트할 때 쓴다.
 * 콜백 ref라 요소가 나중에(로딩 뒤) 그려져도 관찰을 시작한다. IntersectionObserver가 없는 환경(jsdom·구형 WebView)에선
 * 바로 true — 기능이 사라지지 않게.
 */
export function useInView<T extends Element>(
  rootMargin = "200px",
): [(el: T | null) => void, boolean] {
  const [el, setEl] = useState<T | null>(null);
  const [inView, setInView] = useState(() => typeof IntersectionObserver === "undefined");
  const ref = useCallback((node: T | null) => setEl(node), []);

  useEffect(() => {
    if (inView || !el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [el, inView, rootMargin]);

  return [ref, inView];
}
