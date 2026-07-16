import { X } from "lucide-react";
import { ReactNode, useId } from "react";
import { useModalBehavior } from "@/hooks/useModalBehavior";

const SIZE_CLASSES = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

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
  const { dialogRef, overlayRef } = useModalBehavior(onClose);
  const titleId = useId();

  return (
    <div
      ref={overlayRef}
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
        <div className="sm:hidden flex justify-center pt-2 pb-1 shrink-0" aria-hidden="true">
          <div className="w-9 h-1 rounded-full bg-gray-300 dark:bg-gray-600" />
        </div>
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
