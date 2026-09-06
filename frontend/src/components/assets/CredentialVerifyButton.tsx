import { CheckCircle, XCircle } from "lucide-react";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import type { CredentialVerifyState } from "@/hooks/createCredentialVerify";

interface Props {
  /** 자격증명 입력값이 채워졌는지 등 표시 조건 (브로커별로 상이) */
  show: boolean;
  /** 검증 요청 불가 조건 (필수 입력 미완 등) */
  disabled: boolean;
  verifyState: CredentialVerifyState;
  verifyError: string;
  onVerify: () => void;
}

/** 브로커 자격증명 "확인" 버튼 + 결과 표시 — KIS/토스 자격증명 입력 폼 공용. */
export default function CredentialVerifyButton({
  show,
  disabled,
  verifyState,
  verifyError,
  onVerify,
}: Props) {
  if (!show) return null;
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={onVerify}
        disabled={verifyState === "loading" || disabled}
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors`}
      >
        {verifyState === "loading" ? "확인 중..." : "자격증명 확인"}
      </button>
      {verifyState === "ok" && (
        <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
          <CheckCircle size={14} /> 자격증명 확인됨
        </span>
      )}
      {verifyState === "error" && (
        <span className="flex items-center gap-1 text-xs text-red-500">
          <XCircle size={14} /> {verifyError}
        </span>
      )}
    </div>
  );
}
