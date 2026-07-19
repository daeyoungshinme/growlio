import { Bell, Zap } from "lucide-react";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

interface ExistingAlertLike {
  mode?: "NOTIFY" | "AUTO";
  threshold_pct?: number;
}

interface Props {
  existingAlert?: ExistingAlertLike;
  onOpenAlertModal: () => void;
  /** true면 PortfolioListSection 카드 푸터의 아이콘+배지 버튼 변형을 렌더링한다. */
  compact?: boolean;
}

export default function AutomationStatusBar({ existingAlert, onOpenAlertModal, compact }: Props) {
  const hasAlert = !!existingAlert;
  const isAuto = existingAlert?.mode === "AUTO";

  if (compact) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          onOpenAlertModal();
        }}
        title="리밸런싱 자동화 설정"
        aria-label="리밸런싱 자동화 설정"
        className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-0.5 px-2 py-1 rounded-lg transition-colors text-xs font-medium ${
          isAuto
            ? "bg-orange-100 dark:bg-orange-950 text-orange-600 dark:text-orange-400 hover:bg-orange-200 dark:hover:bg-orange-900"
            : hasAlert
              ? "bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-900"
              : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
        }`}
      >
        {isAuto ? <Zap size={11} /> : <Bell size={11} />}
        <span>{isAuto ? "자동" : hasAlert ? "알림" : "자동화 설정"}</span>
      </button>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 p-3 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-sm">
      {existingAlert ? (
        <span
          className={`flex items-center gap-1.5 text-xs ${isAuto ? "text-orange-600 dark:text-orange-400" : "text-blue-600 dark:text-blue-400"}`}
        >
          <Bell size={12} />
          {isAuto
            ? `자동 실행 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`
            : `알림 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`}
        </span>
      ) : (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          이 포트폴리오에 자동화를 설정하시겠어요?
        </span>
      )}
      <button
        onClick={onOpenAlertModal}
        className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} self-end sm:self-auto text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap sm:ml-3`}
      >
        {existingAlert ? "설정 변경" : "자동화 설정"}
      </button>
    </div>
  );
}
