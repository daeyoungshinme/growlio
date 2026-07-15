import { CheckCircle, XCircle } from "lucide-react";
import type { AssetAccountCreate } from "@/api/assets";
import { INPUT_SM } from "@/constants/inputStyles";
import { useForm } from "@/hooks/useForm";

interface Props {
  form: AssetAccountCreate;
  set: ReturnType<typeof useForm<AssetAccountCreate>>["set"];
  isEdit: boolean;
  kisAccountNoValid: boolean;
  verifyState: "idle" | "loading" | "ok" | "error";
  verifyError: string;
  onVerify: () => void;
  onCredentialChange: () => void;
}

// KIS(한국투자증권) 자격증명 입력 + 검증 버튼
export default function KisCredentialFields({
  form,
  set,
  isEdit,
  kisAccountNoValid,
  verifyState,
  verifyError,
  onVerify,
  onCredentialChange,
}: Props) {
  return (
    <>
      {!isEdit && (
        <div>
          <label
            htmlFor="stock-kis-account-no"
            className="text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            KIS 계좌번호 *
          </label>
          <input
            id="stock-kis-account-no"
            className={`mt-1 w-full ${INPUT_SM}`}
            value={form.kis_account_no ?? ""}
            onChange={(e) => set("kis_account_no", e.target.value)}
            placeholder="12345678-01"
            autoComplete="off"
          />
          {form.kis_account_no && !kisAccountNoValid && (
            <p className="mt-1 text-xs text-red-500">형식 오류: 12345678-01 형식으로 입력하세요</p>
          )}
        </div>
      )}
      <div>
        <label
          htmlFor="stock-kis-app-key"
          className="text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          KIS App Key{!isEdit && " *"}
        </label>
        {isEdit && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 mb-1">
            비워두면 기존 키를 유지합니다
          </p>
        )}
        <input
          id="stock-kis-app-key"
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={form.kis_app_key ?? ""}
          onChange={(e) => {
            set("kis_app_key", e.target.value);
            onCredentialChange();
          }}
          placeholder={isEdit ? "기존 키 유지" : "KIS 앱 키"}
          autoComplete="off"
        />
      </div>
      <div>
        <label
          htmlFor="stock-kis-app-secret"
          className="text-sm font-medium text-gray-700 dark:text-gray-300"
        >
          KIS App Secret{!isEdit && " *"}
        </label>
        <input
          id="stock-kis-app-secret"
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={form.kis_app_secret ?? ""}
          onChange={(e) => {
            set("kis_app_secret", e.target.value);
            onCredentialChange();
          }}
          placeholder={isEdit ? "기존 시크릿 유지" : "KIS 앱 시크릿"}
          autoComplete="off"
        />
      </div>
      {(!isEdit || form.kis_app_key || form.kis_app_secret) && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onVerify}
            disabled={verifyState === "loading" || !form.kis_app_key || !form.kis_app_secret}
            className="px-3 py-1.5 text-xs border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
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
      )}
    </>
  );
}
