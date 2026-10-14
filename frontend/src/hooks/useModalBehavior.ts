import { useEffect, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

// 모달이 겹쳐 열릴 수 있으므로(예: 계좌별 자동화 목록 위에 편집 모달) 참조 카운트로 body 스크롤 잠금 관리
let bodyLockCount = 0;
let savedBodyOverflow = "";
// 열린 모달 목록 — Escape/포커스 트랩은 맨 위 모달만 처리한다.
// (Android 뒤로가기는 Escape를 dispatch하므로, 이게 없으면 확인창 위에서 한 번 눌러도 아래 모달까지 함께 닫힘)
interface ModalEntry {
  overlay: () => HTMLElement | null;
}
const openModals: ModalEntry[] = [];

// 맨 위 판정: DOM상 다른 열린 모달을 품고 있으면 아래층(같이 마운트되면 자식 effect가 먼저 돌아 등록 순서가 뒤집힘),
// 서로 품지 않는 형제 모달끼리는 나중에 열린 쪽이 위.
function isTopModal(me: ModalEntry): boolean {
  const myEl = me.overlay();
  return openModals.every((other) => {
    if (other === me) return true;
    const otherEl = other.overlay();
    if (myEl && otherEl) {
      if (myEl.contains(otherEl)) return false;
      if (otherEl.contains(myEl)) return true;
    }
    return openModals.indexOf(other) < openModals.indexOf(me);
  });
}

export function useModalBehavior(onClose: () => void) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (bodyLockCount === 0) {
      savedBodyOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    bodyLockCount++;
    return () => {
      bodyLockCount--;
      if (bodyLockCount === 0) {
        document.body.style.overflow = savedBodyOverflow;
      }
    };
  }, []);

  // 상위 mainRef의 pull-to-refresh/스와이프 탭전환 리스너로 터치가 새어나가지 않도록 여기서 소비함
  useEffect(() => {
    const el = overlayRef.current;
    if (!el) return;
    const stopPropagation = (e: TouchEvent) => e.stopPropagation();
    el.addEventListener("touchstart", stopPropagation, { passive: true });
    el.addEventListener("touchmove", stopPropagation, { passive: true });
    el.addEventListener("touchend", stopPropagation, { passive: true });
    return () => {
      el.removeEventListener("touchstart", stopPropagation);
      el.removeEventListener("touchmove", stopPropagation);
      el.removeEventListener("touchend", stopPropagation);
    };
  }, []);

  useEffect(() => {
    const entry: ModalEntry = { overlay: () => overlayRef.current };
    openModals.push(entry);
    const prevFocus = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    if (dialog) {
      const focusable = dialog.querySelectorAll<HTMLElement>(FOCUSABLE);
      focusable[0]?.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isTopModal(entry)) return;
      if (e.key === "Escape") {
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !dialog) return;
      const els = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (els.length === 0) return;
      if (e.shiftKey) {
        if (document.activeElement === els[0]) {
          e.preventDefault();
          els[els.length - 1].focus();
        }
      } else {
        if (document.activeElement === els[els.length - 1]) {
          e.preventDefault();
          els[0].focus();
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      const idx = openModals.indexOf(entry);
      if (idx !== -1) openModals.splice(idx, 1);
      prevFocus?.focus();
    };
  }, []);

  return { dialogRef, overlayRef };
}
