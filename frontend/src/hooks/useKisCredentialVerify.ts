import { useState } from "react";
import { verifyKisCredentials } from "@/api/assets";
import { extractErrorMessage } from "@/utils/error";

export function useKisCredentialVerify() {
  const [verifyState, setVerifyState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [verifyError, setVerifyError] = useState("");

  const verify = async (appKey: string, appSecret: string, isMock: boolean) => {
    setVerifyState("loading");
    try {
      await verifyKisCredentials({ kis_app_key: appKey, kis_app_secret: appSecret, is_mock: isMock });
      setVerifyState("ok");
    } catch (e) {
      setVerifyState("error");
      setVerifyError(extractErrorMessage(e, "자격증명 확인 실패"));
    }
  };

  const reset = () => setVerifyState("idle");

  return { verifyState, verifyError, verify, reset };
}
