import { LineChart } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { INPUT_SM } from "@/constants/inputStyles";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const forgotPassword = useAuthStore((s) => s.forgotPassword);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await forgotPassword(email.trim());
      setSubmitted(true);
    } catch {
      setError("요청 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
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

        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-1">비밀번호 찾기</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
          가입한 이메일 주소를 입력하면 비밀번호 재설정 링크를 보내드립니다.
        </p>

        {submitted ? (
          <div className="p-4 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700">
            <p className="text-sm text-blue-700 dark:text-blue-300 text-center">
              이메일을 확인해주세요.<br />비밀번호 재설정 링크를 보내드렸습니다.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">이메일</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className={`w-full ${INPUT_SM}`}
              />
            </div>

            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "전송 중..." : "재설정 링크 발송"}
            </button>
          </form>
        )}

        <div className="mt-6 flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <Link to="/find-account" className="text-blue-600 dark:text-blue-400 hover:underline">
            아이디 찾기
          </Link>
          <Link to="/login" className="hover:underline">
            로그인으로 돌아가기
          </Link>
        </div>
      </div>
    </div>
  );
}
