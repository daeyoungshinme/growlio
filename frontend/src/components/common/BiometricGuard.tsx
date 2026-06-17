import { useEffect } from "react";
import { Fingerprint, RefreshCw, ShieldAlert } from "lucide-react";
import { useBiometric } from "@/hooks/useBiometric";
import { isNativePlatform } from "@/utils/platform";

interface Props {
  children: React.ReactNode;
}

export default function BiometricGuard({ children }: Props) {
  const { isVerified, isAvailable, isEnabled, isLoading, error, verify } = useBiometric();

  // 생체 인증이 활성화된 네이티브 환경에서 미인증 상태면 자동으로 프롬프트 표시
  useEffect(() => {
    if (isNativePlatform() && isEnabled && isAvailable && !isVerified) {
      void verify();
    }
  }, [isEnabled, isAvailable, isVerified, verify]);

  // 웹 환경이거나 생체 인증 비활성화 상태면 바로 통과
  if (!isNativePlatform() || !isEnabled || !isAvailable || isVerified) {
    return <>{children}</>;
  }

  return (
    <div className="fixed inset-0 flex flex-col items-center justify-center bg-slate-900 z-50 px-6">
      <div className="flex flex-col items-center gap-6 text-center max-w-xs w-full">
        <div className="w-20 h-20 rounded-full bg-blue-600/20 flex items-center justify-center">
          {error ? (
            <ShieldAlert size={36} className="text-red-400" aria-hidden="true" />
          ) : (
            <Fingerprint size={36} className="text-blue-400" aria-hidden="true" />
          )}
        </div>

        <div className="space-y-2">
          <h1 className="text-xl font-semibold text-slate-100">
            {error ? "인증 실패" : "Growlio"}
          </h1>
          <p className="text-sm text-slate-400">{error ?? "생체 인증으로 계속하세요"}</p>
        </div>

        <button
          onClick={() => void verify()}
          disabled={isLoading}
          className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors w-full justify-center"
          aria-busy={isLoading}
        >
          {isLoading ? (
            <RefreshCw size={16} className="animate-spin" aria-hidden="true" />
          ) : (
            <Fingerprint size={16} aria-hidden="true" />
          )}
          {isLoading ? "인증 중..." : error ? "다시 시도" : "인증하기"}
        </button>
      </div>
    </div>
  );
}
