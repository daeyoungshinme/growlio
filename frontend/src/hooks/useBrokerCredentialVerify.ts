import type { AssetAccountCreate } from "@/api/assets";
import type { BrokerDataSource } from "@/constants/brokerCredentials";
import type { CredentialVerifyState } from "@/hooks/createCredentialVerify";
import { useKisCredentialVerify } from "@/hooks/useKisCredentialVerify";
import { useKiwoomCredentialVerify } from "@/hooks/useKiwoomCredentialVerify";
import { useTossCredentialVerify } from "@/hooks/useTossCredentialVerify";

export interface BrokerVerifyHandle {
  verifyState: CredentialVerifyState;
  verifyError: string;
  onVerify: () => void;
  reset: () => void;
}

/** KIS/키움/토스 자격증명 검증 훅 3개를 브로커별 핸들로 묶는다 — 검증 API 인자 형태(모의투자
 * 여부 포함 여부)만 브로커마다 달라 현재 폼 값에서 꺼내 넘긴다. 키/시크릿이 비어 있으면 호출하지 않는다. */
export function useBrokerCredentialVerify(
  form: AssetAccountCreate,
): Record<BrokerDataSource, BrokerVerifyHandle> {
  const kis = useKisCredentialVerify();
  const kiwoom = useKiwoomCredentialVerify();
  const toss = useTossCredentialVerify();
  const isMock = form.is_mock_mode ?? true;

  return {
    KIS_API: {
      verifyState: kis.verifyState,
      verifyError: kis.verifyError,
      onVerify: () => {
        if (!form.kis_app_key || !form.kis_app_secret) return;
        void kis.verify(form.kis_app_key, form.kis_app_secret, isMock);
      },
      reset: kis.reset,
    },
    KIWOOM_API: {
      verifyState: kiwoom.verifyState,
      verifyError: kiwoom.verifyError,
      onVerify: () => {
        if (!form.kiwoom_app_key || !form.kiwoom_app_secret) return;
        void kiwoom.verify(form.kiwoom_app_key, form.kiwoom_app_secret, isMock);
      },
      reset: kiwoom.reset,
    },
    TOSS_API: {
      verifyState: toss.verifyState,
      verifyError: toss.verifyError,
      onVerify: () => {
        if (!form.toss_client_id || !form.toss_client_secret) return;
        void toss.verify(form.toss_client_id, form.toss_client_secret);
      },
      reset: toss.reset,
    },
  };
}
