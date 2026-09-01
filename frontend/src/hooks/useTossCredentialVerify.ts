import { useState } from "react";
import { verifyTossCredentials } from "@/api/assets";
import { extractErrorMessage } from "@/utils/error";

export function useTossCredentialVerify() {
  const [verifyState, setVerifyState] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [verifyError, setVerifyError] = useState("");

  const verify = async (clientId: string, clientSecret: string) => {
    setVerifyState("loading");
    try {
      await verifyTossCredentials({
        toss_client_id: clientId,
        toss_client_secret: clientSecret,
      });
      setVerifyState("ok");
    } catch (e) {
      setVerifyState("error");
      setVerifyError(extractErrorMessage(e, "자격증명 확인 실패"));
    }
  };

  const reset = () => setVerifyState("idle");

  return { verifyState, verifyError, verify, reset };
}
