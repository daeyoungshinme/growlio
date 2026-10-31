import { useEffect } from "react";
import { SCROLL_INTO_VIEW_DELAY } from "@/constants/timers";

const isTextEntry = (el: EventTarget | null): el is HTMLElement =>
  el instanceof HTMLInputElement ||
  el instanceof HTMLTextAreaElement ||
  el instanceof HTMLSelectElement;

/** 포커스된 입력이 키보드(visualViewport 하단) 아래에 가려 있으면 화면 가운데로 올린다.
 * Android adjustResize만으로는 스크롤 컨테이너(<main>·모달 본문) 안쪽 입력까지 끌어올리지 못한다.
 * 앱 셸에서 한 번만 등록한다 — 입력마다 붙이지 않는다. */
export function useRevealFocusedInput() {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let timer: number | undefined;
    const onFocusIn = (e: FocusEvent) => {
      const el = e.target;
      if (!isTextEntry(el)) return;
      window.clearTimeout(timer);
      // 키보드가 다 올라온 뒤의 뷰포트로 판정한다
      timer = window.setTimeout(() => {
        if (document.activeElement !== el) return;
        if (el.getBoundingClientRect().bottom > vv.offsetTop + vv.height) {
          el.scrollIntoView({ block: "center" });
        }
      }, SCROLL_INTO_VIEW_DELAY);
    };
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("focusin", onFocusIn);
      window.clearTimeout(timer);
    };
  }, []);
}
