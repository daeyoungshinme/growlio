import { Info } from "lucide-react";
import type { AssetAccountCreate } from "@/api/assets";
import { INPUT_SM } from "@/constants/inputStyles";
import { useForm } from "@/hooks/useForm";
import CredentialVerifyButton from "./CredentialVerifyButton";

interface Props {
  form: AssetAccountCreate;
  set: ReturnType<typeof useForm<AssetAccountCreate>>["set"];
  isEdit: boolean;
  verifyState: "idle" | "loading" | "ok" | "error";
  verifyError: string;
  onVerify: () => void;
  onCredentialChange: () => void;
}

// 토스증권 Open API 자격증명 입력 + 검증 버튼
export default function TossCredentialFields({
  form,
  set,
  isEdit,
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
            htmlFor="stock-toss-account-no"
            className="text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            토스증권 계좌번호 *
          </label>
          <input
            id="stock-toss-account-no"
            className={`mt-1 w-full ${INPUT_SM}`}
            value={form.toss_account_no ?? ""}
            onChange={(e) => set("toss_account_no", e.target.value)}
            placeholder="토스증권 계좌번호"
            autoComplete="off"
          />
        </div>
      )}
      <div>
        <label
          htmlFor="stock-toss-client-id"
          className="text-sm font-medium text-gray-600 dark:text-gray-400"
        >
          토스 Client ID{!isEdit && " *"}
        </label>
        {isEdit && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 mb-1">
            비워두면 기존 값을 유지합니다
          </p>
        )}
        <input
          id="stock-toss-client-id"
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={form.toss_client_id ?? ""}
          onChange={(e) => {
            set("toss_client_id", e.target.value || undefined);
            onCredentialChange();
          }}
          placeholder={isEdit ? "기존 값 유지" : "토스 Client ID"}
          autoComplete="off"
        />
      </div>
      <div>
        <label
          htmlFor="stock-toss-client-secret"
          className="text-sm font-medium text-gray-600 dark:text-gray-400"
        >
          토스 Client Secret{!isEdit && " *"}
        </label>
        <input
          id="stock-toss-client-secret"
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={form.toss_client_secret ?? ""}
          onChange={(e) => {
            set("toss_client_secret", e.target.value || undefined);
            onCredentialChange();
          }}
          placeholder={isEdit ? "기존 값 유지" : "토스 Client Secret"}
          autoComplete="off"
        />
      </div>

      <CredentialVerifyButton
        show={!isEdit || !!form.toss_client_id || !!form.toss_client_secret}
        disabled={!form.toss_client_id || !form.toss_client_secret}
        verifyState={verifyState}
        verifyError={verifyError}
        onVerify={onVerify}
      />

      <div className="flex gap-2 rounded-lg bg-blue-50 dark:bg-blue-950/40 p-2.5 text-xs text-blue-700 dark:text-blue-300">
        <Info size={14} className="mt-0.5 shrink-0" />
        <div className="space-y-1">
          <p>
            토스증권 웹( <span className="font-mono">전체 &rarr; Open API &rarr; 신청</span>)에서
            Client ID·Secret을 발급하세요.
          </p>
          <p>
            토스 <span className="font-mono">Open API &rarr; IP 관리</span>에 Growlio 서버 IP를
            등록해야 조회가 됩니다. 미등록 시 "IP 관리" 오류가 표시됩니다.
          </p>
        </div>
      </div>
    </>
  );
}
