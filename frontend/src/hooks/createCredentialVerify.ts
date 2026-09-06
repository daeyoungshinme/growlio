import { useCallback, useState } from "react";
import { extractErrorMessage } from "@/utils/error";

export type CredentialVerifyState = "idle" | "loading" | "ok" | "error";

/** 브로커 자격증명 "확인" 버튼용 상태 머신 팩토리.
 *
 * KIS/토스 등 브로커별 검증 API의 인자 형태만 다르고 상태 전이(idle→loading→ok/error)는
 * 동일하므로, 검증 호출 함수를 받아 훅을 만든다. `apiCall`은 클로저로 감싸 전달해야
 * 부분 모킹된 테스트에서 import 바인딩이 조기 평가되지 않는다(useSettingsToggle 선례).
 */
export function createCredentialVerify<A extends unknown[]>(
  apiCall: (...args: A) => Promise<unknown>,
) {
  return function useCredentialVerify() {
    const [verifyState, setVerifyState] = useState<CredentialVerifyState>("idle");
    const [verifyError, setVerifyError] = useState("");

    const verify = useCallback(async (...args: A) => {
      setVerifyState("loading");
      try {
        await apiCall(...args);
        setVerifyState("ok");
      } catch (e) {
        setVerifyState("error");
        setVerifyError(extractErrorMessage(e, "자격증명 확인 실패"));
      }
    }, []);

    const reset = useCallback(() => setVerifyState("idle"), []);

    return { verifyState, verifyError, verify, reset };
  };
}
