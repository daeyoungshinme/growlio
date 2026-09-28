import { Info } from "lucide-react";
import type { AssetAccountCreate } from "@/api/assets";
import { BROKER_CREDENTIAL_CONFIG, type BrokerDataSource } from "@/constants/brokerCredentials";
import { INPUT_SM } from "@/constants/inputStyles";
import type { CredentialVerifyState } from "@/hooks/createCredentialVerify";
import { useForm } from "@/hooks/useForm";
import CredentialVerifyButton from "./CredentialVerifyButton";

function TossApiNotice() {
  return (
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
  );
}

const LABEL_CLASS = "text-sm font-medium text-gray-700 dark:text-gray-300";

interface Props {
  source: BrokerDataSource;
  form: AssetAccountCreate;
  set: ReturnType<typeof useForm<AssetAccountCreate>>["set"];
  isEdit: boolean;
  /** 계좌번호 형식 오류 메시지 — 형식 검증이 있는 브로커(KIS)만 전달 */
  accountNoError?: string;
  verifyState: CredentialVerifyState;
  verifyError: string;
  onVerify: () => void;
  onCredentialChange: () => void;
}

// 증권사 API 자격증명(계좌번호 + 키/시크릿) 입력 + 검증 버튼
export default function BrokerCredentialFields({
  source,
  form,
  set,
  isEdit,
  accountNoError,
  verifyState,
  verifyError,
  onVerify,
  onCredentialChange,
}: Props) {
  const config = BROKER_CREDENTIAL_CONFIG[source];
  const { accountNo, key, secret } = config;
  const keyValue = form[key.field];
  const secretValue = form[secret.field];
  const accountNoId = `stock-${config.idPrefix}-account-no`;
  const keyId = `stock-${config.idPrefix}-${key.idSuffix}`;
  const secretId = `stock-${config.idPrefix}-${secret.idSuffix}`;

  return (
    <>
      {!isEdit && (
        <div>
          <label htmlFor={accountNoId} className={LABEL_CLASS}>
            {accountNo.label} *
          </label>
          <input
            id={accountNoId}
            className={`mt-1 w-full ${INPUT_SM}`}
            value={form[accountNo.field] ?? ""}
            onChange={(e) => set(accountNo.field, e.target.value)}
            placeholder={accountNo.placeholder}
            autoComplete="off"
          />
          {accountNoError && <p className="mt-1 text-xs text-red-500">{accountNoError}</p>}
        </div>
      )}
      <div>
        <label htmlFor={keyId} className={LABEL_CLASS}>
          {key.label}
          {!isEdit && " *"}
        </label>
        {isEdit && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 mb-1">{config.edit.hint}</p>
        )}
        <input
          id={keyId}
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={keyValue ?? ""}
          onChange={(e) => {
            set(key.field, e.target.value || undefined);
            onCredentialChange();
          }}
          placeholder={isEdit ? config.edit.keyPlaceholder : key.placeholder}
          autoComplete="off"
        />
      </div>
      <div>
        <label htmlFor={secretId} className={LABEL_CLASS}>
          {secret.label}
          {!isEdit && " *"}
        </label>
        <input
          id={secretId}
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={secretValue ?? ""}
          onChange={(e) => {
            set(secret.field, e.target.value || undefined);
            onCredentialChange();
          }}
          placeholder={isEdit ? config.edit.secretPlaceholder : secret.placeholder}
          autoComplete="off"
        />
      </div>
      <CredentialVerifyButton
        show={!isEdit || !!keyValue || !!secretValue}
        disabled={!keyValue || !secretValue}
        verifyState={verifyState}
        verifyError={verifyError}
        onVerify={onVerify}
      />
      {source === "TOSS_API" && <TossApiNotice />}
    </>
  );
}
