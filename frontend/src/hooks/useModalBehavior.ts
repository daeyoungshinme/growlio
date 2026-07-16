import { useEffect, useRef } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

// 모달이 겹쳐 열릴 수 있으므로(예: 계좌별 자동화 목록 위에 편집 모달) 참조 카운트로 body 스크롤 잠금 관리
let bodyLockCount = 0;
let savedBodyOverflow = "";

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
    const prevFocus = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    if (dialog) {
      const focusable = dialog.querySelectorAll<HTMLElement>(FOCUSABLE);
      focusable[0]?.focus();
    }

    const handleKeyDown = (e: KeyboardEvent) => {
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
      prevFocus?.focus();
    };
  }, []);

  return { dialogRef, overlayRef };
}
