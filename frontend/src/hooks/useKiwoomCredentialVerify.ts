import { verifyKiwoomCredentials } from "@/api/assets";
import { createCredentialVerify } from "@/hooks/createCredentialVerify";

export const useKiwoomCredentialVerify = createCredentialVerify(
  (appKey: string, appSecret: string, isMock: boolean) =>
    verifyKiwoomCredentials({
      kiwoom_app_key: appKey,
      kiwoom_app_secret: appSecret,
      is_mock: isMock,
    }),
);
