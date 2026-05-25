import { LineChart } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { supabase } from "../lib/supabase";
import { useAuthStore } from "../stores/authStore";
import { toast } from "../utils/toast";

export default function ResetPasswordPage() {
  const navigate = useNavigate();

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessionReady, setSessionReady] = useState(false);
  const resetPassword = useAuthStore((s) => s.resetPassword);

  useEffect(() => {
    // Supabase가 이메일 링크의 #access_token= 프래그먼트를 감지해 세션 설정
    const { data: subscription } = supabase.auth.onAuthStateChange((event) => {
      if (event === "PASSWORD_RECOVERY") {
        setSessionReady(true);
      }
    });
    return () => subscription.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => navigate("/login"), 3000);
      return () => clearTimeout(timer);
    }
  }, [success, navigate]);

  if (!sessionReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
        <div className="w-full max-w-sm bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            비밀번호 재설정 링크를 확인 중입니다...
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500">
            이메일의 재설정 링크를 클릭해 이 페이지에 접근해야 합니다.
          </p>
          <Link
            to="/forgot-password"
            className="block mt-4 text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            비밀번호 찾기로 돌아가기
          </Link>
        </div>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (newPassword.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("비밀번호가 일치하지 않습니다.");
      return;
    }

    setLoading(true);
    try {
      await resetPassword(newPassword);
      setSuccess(true);
    } catch (err: unknown) {
      const code = (err as { code?: string })?.code;
      const msg = (err as Error)?.message ?? "";
      if (code === "weak_password" || msg.toLowerCase().includes("should not be too common") || msg.toLowerCase().includes("data breach")) {
        toast("유출된 비밀번호입니다. 데이터 유출 사례에서 발견된 비밀번호는 사용할 수 없습니다.", "error");
      } else {
        setError("비밀번호 변경에 실패했습니다. 다시 시도해주세요.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="w-full max-w-sm bg-white dark:bg-gray-900 rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-8">
        <div className="flex items-center gap-2 mb-8 justify-center">
          <LineChart className="text-blue-600 dark:text-blue-400" size={28} />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">Growlio</h1>
        </div>

        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-1">새 비밀번호 설정</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">새로 사용할 비밀번호를 입력해주세요.</p>

        {success ? (
          <div className="p-4 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700">
            <p className="text-sm text-green-700 dark:text-green-300 text-center">
              비밀번호가 변경되었습니다.<br />
              <span className="text-xs text-gray-500 dark:text-gray-400">3초 후 로그인 페이지로 이동합니다...</span>
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">새 비밀번호</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                placeholder="8자 이상"
                className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">비밀번호 확인</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                placeholder="비밀번호 재입력"
                className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "변경 중..." : "비밀번호 변경"}
            </button>
          </form>
        )}

        {!success && (
          <p className="text-center text-xs text-gray-500 dark:text-gray-400 mt-6">
            <Link to="/login" className="hover:underline">로그인으로 돌아가기</Link>
          </p>
        )}
      </div>
    </div>
  );
}
