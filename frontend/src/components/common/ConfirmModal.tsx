import { TriangleAlert } from "lucide-react";
import { useId, type ReactNode } from "react";
import { triggerHaptic } from "@/hooks/useHaptic";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { useModalBehavior } from "@/hooks/useModalBehavior";

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
  // 포커스 트랩·Escape·Android 뒤로가기(=Escape)로 닫기 + body 잠금 — 다른 모달 위에 떠도 맨 위만 닫힌다
  const { dialogRef, overlayRef } = useModalBehavior(onCancel);

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 bg-black/40 flex items-end sm:items-center justify-center z-[70] sm:p-4"
      onClick={onCancel}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={msgId}
        className="bg-white dark:bg-gray-900 rounded-t-2xl sm:rounded-2xl shadow-xl w-full sm:max-w-sm max-h-[85dvh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 본문만 스크롤하고 버튼은 고정 — 비교표 같은 긴 children이 확인 버튼을 화면 밖으로 밀지 않게 (plans/102 A2) */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain flex items-start gap-3 px-6 pt-6 pb-5">
          {danger && (
            <TriangleAlert size={20} className="text-red-500 mt-0.5 shrink-0" aria-hidden="true" />
          )}
          <div className="min-w-0 flex-1">
            <p id={msgId} className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
              {message}
            </p>
            {children}
          </div>
        </div>
        <div className="shrink-0 flex gap-4 justify-end px-6 pb-[calc(1.5rem+env(safe-area-inset-bottom))] sm:pb-6">
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
