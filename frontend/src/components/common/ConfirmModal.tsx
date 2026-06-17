import { AlertTriangle } from "lucide-react";
import { useId } from "react";
import { triggerHaptic } from "@/hooks/useHaptic";

interface Props {
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
}

export default function ConfirmModal({
  message,
  confirmLabel = "확인",
  cancelLabel = "취소",
  onConfirm,
  onCancel,
  danger = true,
}: Props) {
  const msgId = useId();

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-[70] p-4"
      onClick={onCancel}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={msgId}
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl w-full max-w-sm p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-5">
          {danger && (
            <AlertTriangle size={20} className="text-red-500 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          <p id={msgId} className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
            {message}
          </p>
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={() => {
              void triggerHaptic(danger ? "heavy" : "medium");
              onConfirm();
            }}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
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
