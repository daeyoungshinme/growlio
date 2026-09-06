import { verifyTossCredentials } from "@/api/assets";
import { createCredentialVerify } from "@/hooks/createCredentialVerify";

export const useTossCredentialVerify = createCredentialVerify(
  (clientId: string, clientSecret: string) =>
    verifyTossCredentials({ toss_client_id: clientId, toss_client_secret: clientSecret }),
);
