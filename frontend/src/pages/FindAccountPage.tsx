import { LineChart } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStore } from "../stores/authStore";
import { INPUT_SM } from "../constants/inputStyles";

export default function FindAccountPage() {
  const [displayName, setDisplayName] = useState("");
  const [results, setResults] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const findAccount = useAuthStore((s) => s.findAccount);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setResults(null);
    setLoading(true);
    try {
      const emails = await findAccount(displayName.trim());
      setResults(emails);
    } catch {
      setError("조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
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

        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-100 mb-1">아이디 찾기</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">가입 시 등록한 이름으로 이메일 주소를 확인합니다.</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">이름</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
              placeholder="가입 시 사용한 이름"
              className={`w-full ${INPUT_SM}`}
            />
          </div>

          {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}

          <button
            type="submit"
            disabled={loading || !displayName.trim()}
            className="w-full bg-blue-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {loading ? "조회 중..." : "이메일 확인"}
          </button>
        </form>

        {results !== null && (
          <div className="mt-6 p-4 rounded-lg bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">
            {results.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center">
                일치하는 계정을 찾을 수 없습니다.
              </p>
            ) : (
              <>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">가입된 이메일 계정</p>
                <ul className="space-y-1">
                  {results.map((email, idx) => (
                    <li key={idx} className="text-sm font-medium text-gray-800 dark:text-gray-100">
                      {email}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-between text-xs text-gray-500 dark:text-gray-400">
          <Link to="/forgot-password" className="text-blue-600 dark:text-blue-400 hover:underline">
            비밀번호 찾기
          </Link>
          <Link to="/login" className="hover:underline">
            로그인으로 돌아가기
          </Link>
        </div>
      </div>
    </div>
  );
}
