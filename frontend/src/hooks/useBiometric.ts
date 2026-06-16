import { useCallback, useEffect, useRef, useState } from "react";
import { isNativePlatform } from "@/utils/platform";
import { useHaptic } from "./useHaptic";

const STORAGE_KEY = "growlio_biometric_enabled";
const SESSION_KEY = "growlio_biometric_verified";

export function useBiometric() {
  const { impact } = useHaptic();

  // 이번 세션에서 이미 인증했는지 (앱 재시작 시 초기화됨)
  const [isVerified, setIsVerified] = useState(
    () => sessionStorage.getItem(SESSION_KEY) === "1",
  );
  const [isAvailable, setIsAvailable] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEnabled = localStorage.getItem(STORAGE_KEY) === "1";

  const availabilityChecked = useRef(false);

  useEffect(() => {
    if (!isNativePlatform() || availabilityChecked.current) return;
    availabilityChecked.current = true;

    async function check() {
      try {
        const { NativeBiometric } = await import("capacitor-native-biometric");
        const result = await NativeBiometric.isAvailable();
        setIsAvailable(result.isAvailable);
      } catch {
        setIsAvailable(false);
      }
    }
    void check();
  }, []);

  const verify = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { NativeBiometric } = await import("capacitor-native-biometric");
      await NativeBiometric.verifyIdentity({
        reason: "Growlio 앱 인증",
        title: "생체 인증",
        subtitle: "지문 또는 얼굴로 로그인하세요",
        description: "저장된 자산 정보를 확인하려면 인증이 필요합니다",
        maxAttempts: 3,
      });
      sessionStorage.setItem(SESSION_KEY, "1");
      setIsVerified(true);
      impact("success");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "인증에 실패했습니다";
      setError(msg);
      impact("error");
    } finally {
      setIsLoading(false);
    }
  }, [impact]);

  const setEnabled = useCallback((enabled: boolean) => {
    if (enabled) {
      localStorage.setItem(STORAGE_KEY, "1");
    } else {
      localStorage.removeItem(STORAGE_KEY);
      sessionStorage.setItem(SESSION_KEY, "1");
      setIsVerified(true);
    }
  }, []);

  return { isVerified, isAvailable, isEnabled, isLoading, error, verify, setEnabled };
}
