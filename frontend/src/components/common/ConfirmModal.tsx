import { AlertTriangle } from "lucide-react";
import { useId, type ReactNode } from "react";
import { triggerHaptic } from "@/hooks/useHaptic";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";

interface Props {
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
  /** 메시지 아래, 버튼 위에 추가로 렌더할 내용(비교 테이블 등) — 생략 시 기존과 동일. */
  children?: ReactNode;
}

export default function ConfirmModal({
  message,
  confirmLabel = "확인",
  cancelLabel = "취소",
  onConfirm,
  onCancel,
  danger = true,
  children,
}: Props) {
  const msgId = useId();

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-[70] sm:p-4"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={msgId}
        className="bg-white dark:bg-gray-900 rounded-t-2xl sm:rounded-2xl shadow-xl w-full sm:max-w-sm p-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] sm:pb-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-5">
          {danger && (
            <AlertTriangle size={20} className="text-red-500 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          <div className="min-w-0 flex-1">
            <p id={msgId} className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
              {message}
            </p>
            {children}
          </div>
        </div>
        <div className="flex gap-4 justify-end">
          <button
            onClick={onCancel}
            className={`${TOUCH_TARGET_MIN} px-4 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
          >
            {cancelLabel}
          </button>
          <button
            onClick={() => {
              void triggerHaptic(danger ? "heavy" : "medium");
              onConfirm();
            }}
            className={`${TOUCH_TARGET_MIN} px-4 text-sm font-medium rounded-lg transition-colors ${
              danger
                ? "bg-red-600 text-white hover:bg-red-700"
                : "bg-blue-600 text-white hover:bg-blue-700"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
