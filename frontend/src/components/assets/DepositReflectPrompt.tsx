import { fmtKrw } from "@/utils/format";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props {
  depositKrw: number;
  amount: number;
  txType: string;
  onApply: (next: number) => void;
  onSkip: () => void;
  className?: string;
}

// 거래 저장 후 "예수금에 반영할까요?" 확인 팝업
export default function DepositReflectPrompt({
  depositKrw,
  amount,
  txType,
  onApply,
  onSkip,
  className = "mx-6 mb-1 rounded-lg p-3",
}: Props) {
  const next = Math.max(0, depositKrw + (txType === "WITHDRAWAL" ? -amount : amount));

  return (
    <div
      className={`bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 ${className}`}
    >
      <p className="text-xs font-medium text-blue-800 dark:text-blue-300 mb-1">
        예수금에 반영할까요?
      </p>
      <p className="text-xs text-blue-600 dark:text-blue-400 mb-2">
        {fmtKrw(depositKrw)}
        {" → "}
        {fmtKrw(next)}
        {" ("}
        {txType === "WITHDRAWAL" ? "-" : "+"}
        {fmtKrw(amount)}
        {")"}
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => onApply(next)}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors`}
        >
          반영
        </button>
        <button
          onClick={onSkip}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 text-gray-500 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors`}
        >
          건너뜀
        </button>
      </div>
    </div>
  );
}
