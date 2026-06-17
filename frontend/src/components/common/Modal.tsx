import { X } from "lucide-react";
import { ReactNode, useEffect, useId, useRef } from "react";

const SIZE_CLASSES = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface Props {
  children: ReactNode;
  onClose: () => void;
  title?: string;
  size?: keyof typeof SIZE_CLASSES;
  closeOnBackdrop?: boolean;
}

export default function Modal({
  children,
  onClose,
  title,
  size = "md",
  closeOnBackdrop = false,
}: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const titleId = useId();
  useEffect(() => {
    onCloseRef.current = onClose;
  });

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

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-[60] sm:p-4 pb-[env(safe-area-inset-bottom)]"
      onClick={closeOnBackdrop ? onClose : undefined}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title != null ? titleId : undefined}
        className={`bg-white dark:bg-gray-900 rounded-t-2xl sm:rounded-2xl shadow-xl w-full ${SIZE_CLASSES[size]} max-h-[85dvh] flex flex-col overscroll-contain`}
        onClick={(e) => e.stopPropagation()}
      >
        {title != null && (
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <h2 id={titleId} className="text-lg font-bold text-gray-900 dark:text-gray-50">
              {title}
            </h2>
            <button
              onClick={onClose}
              aria-label="닫기"
              className="p-2.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
            >
              <X size={18} className="text-gray-500 dark:text-gray-400" />
            </button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}
