import { verifyKisCredentials } from "@/api/assets";
import { createCredentialVerify } from "@/hooks/createCredentialVerify";

export const useKisCredentialVerify = createCredentialVerify(
  (appKey: string, appSecret: string, isMock: boolean) =>
    verifyKisCredentials({ kis_app_key: appKey, kis_app_secret: appSecret, is_mock: isMock }),
);
