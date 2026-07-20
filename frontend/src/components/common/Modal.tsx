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
  /** true면 모바일(<sm)에서 오버레이가 하단 네비게이션 위 공간까지만 채워, 네비가 계속 보이고 탭 가능한 상태로 유지된다 (긴 실행 흐름 중 이탈 허용 용도). 데스크탑(sm+)은 항상 inset-0. */
  avoidBottomNav?: boolean;
}

export default function Modal({
  children,
  onClose,
  title,
  size = "md",
  closeOnBackdrop = false,
  avoidBottomNav = false,
}: Props) {
  const { dialogRef, overlayRef } = useModalBehavior(onClose);
  const titleId = useId();

  const overlayPositionClass = avoidBottomNav
    ? "fixed inset-x-0 top-0 bottom-[calc(3.75rem+env(safe-area-inset-bottom))] sm:inset-0"
    : "fixed inset-0 pb-[env(safe-area-inset-bottom)]";
  const overlayZClass = avoidBottomNav ? "z-40 sm:z-[60]" : "z-[60]";

  return (
    <div
      ref={overlayRef}
      className={`${overlayPositionClass} bg-black/40 flex items-end sm:items-center justify-center ${overlayZClass} sm:p-4`}
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
