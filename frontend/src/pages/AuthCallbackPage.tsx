import { LineChart, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { supabase } from "@/lib/supabase";
import { useAuthStore } from "@/stores/authStore";
import { REDIRECT_DELAY_MS } from "@/constants/timers";

// 다른 기기/브라우저에서 링크를 열어 PKCE code_verifier가 없는 경우 등
// SIGNED_IN 이벤트가 영영 오지 않을 수 있어 무한 대기를 방지
const AUTH_CALLBACK_TIMEOUT_MS = 5000;

function parseHashParams(): URLSearchParams {
  const hash = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  return new URLSearchParams(hash);
}

// Supabase는 인증 실패 시 쿼리(PKCE) 또는 해시(implicit) 양쪽 중 하나에
// error/error_description을 붙여 리다이렉트하므로 둘 다 확인
function getRedirectErrorMessage(searchParams: URLSearchParams): string | null {
  const hashParams = parseHashParams();
  const error = searchParams.get("error") ?? hashParams.get("error");
  const errorDescription =
    searchParams.get("error_description") ?? hashParams.get("error_description");
  if (!error && !errorDescription) return null;
  return errorDescription ?? "인증 링크가 유효하지 않습니다.";
}

type CallbackState = "checking" | "success" | "error";

export default function AuthCallbackPage() {
  const [searchParams] = useSearchParams();
  // 리다이렉트 URL의 에러 파라미터는 마운트 시점에 고정이므로 lazy 초기값으로 한 번만 계산
  const [initialError] = useState(() => getRedirectErrorMessage(searchParams));
  const [state, setState] = useState<CallbackState>(initialError ? "error" : "checking");
  const [errorMessage, setErrorMessage] = useState(initialError ?? "");
  const navigate = useNavigate();
  const checkAuth = useAuthStore((s) => s.checkAuth);
  const settledRef = useRef(!!initialError);

  useEffect(() => {
    if (initialError) return;

    const settleSuccess = async () => {
      if (settledRef.current) return;
      settledRef.current = true;
      window.clearTimeout(timeout);
      await checkAuth();
      setState("success");
    };

    const timeout = window.setTimeout(() => {
      if (settledRef.current) return;
      settledRef.current = true;
      setErrorMessage(
        "이 기기에서 인증을 완료할 수 없습니다. 가입할 때 사용한 브라우저에서 다시 시도하거나, 로그인 화면에서 인증 메일을 재발송해주세요.",
      );
      setState("error");
    }, AUTH_CALLBACK_TIMEOUT_MS);

    const { data: subscription } = supabase.auth.onAuthStateChange((event) => {
      if (event === "SIGNED_IN") void settleSuccess();
    });

    // detectSessionInUrl이 마운트 이전에 이미 세션을 세팅했을 수 있으므로 즉시 한 번 더 확인
    void supabase.auth.getSession().then(({ data: { session } }) => {
      if (session?.user) void settleSuccess();
    });

    return () => {
      window.clearTimeout(timeout);
      subscription.subscription.unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 마운트 시 1회만 URL 파라미터를 확인
  }, []);

  useEffect(() => {
    if (state === "success") {
      const timer = setTimeout(() => navigate("/dashboard"), REDIRECT_DELAY_MS);
      return () => clearTimeout(timer);
    }
  }, [state, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 px-4">
      <div className="w-full max-w-sm bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
        <div className="flex items-center gap-2 mb-6 justify-center">
          <LineChart className="text-blue-600 dark:text-blue-400" size={28} />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Growlio</h1>
        </div>

        {state === "checking" && (
          <div className="flex flex-col items-center gap-3" role="status" aria-label="로딩 중">
            <Loader2 size={24} className="animate-spin text-blue-500" aria-hidden="true" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              이메일 인증을 확인하는 중입니다...
            </p>
          </div>
        )}

        {state === "success" && (
          <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700">
            <p className="text-sm text-green-700 dark:text-green-300">
              이메일 인증이 완료되었습니다.
              <br />
              <span className="text-xs text-gray-500 dark:text-gray-400">
                잠시 후 대시보드로 이동합니다...
              </span>
            </p>
          </div>
        )}

        {state === "error" && (
          <div className="space-y-4">
            <div className="p-4 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700">
              <p className="text-sm text-red-700 dark:text-red-300">{errorMessage}</p>
            </div>
            <div className="flex justify-center gap-4 text-sm">
              <Link to="/login" className="text-blue-600 dark:text-blue-400 hover:underline">
                로그인으로 이동
              </Link>
              <Link to="/register" className="text-blue-600 dark:text-blue-400 hover:underline">
                다시 가입하기
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
