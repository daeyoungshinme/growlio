import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import BottomNav from "./BottomNav";
import { useAuthStore } from "../../stores/authStore";
import { toast } from "../../utils/toast";

export default function AppLayout() {
  const needsPasswordReset = useAuthStore((s) => s.needsPasswordReset);
  const email = useAuthStore((s) => s.email);
  const forgotPassword = useAuthStore((s) => s.forgotPassword);

  const handleSendResetEmail = async () => {
    if (!email) return;
    try {
      await forgotPassword(email);
      toast("비밀번호 재설정 이메일을 발송했습니다. 받은 편지함을 확인해주세요.", "success");
    } catch {
      toast("이메일 발송에 실패했습니다. 잠시 후 다시 시도해주세요.", "error");
    }
  };

  return (
    <div className="flex h-screen bg-gray-50 dark:bg-gray-950">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {needsPasswordReset && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-700 px-4 py-2 text-sm text-yellow-800 dark:text-yellow-300 flex items-center justify-between">
            <span>보안 업그레이드로 인해 비밀번호 재설정이 필요합니다.</span>
            <button
              onClick={handleSendResetEmail}
              className="ml-4 underline font-medium hover:text-yellow-900 dark:hover:text-yellow-200 transition-colors"
            >
              재설정 이메일 받기
            </button>
          </div>
        )}
        <main className="flex-1 overflow-auto p-6 pb-20 lg:pb-6">
          <Outlet />
        </main>
      </div>
      <BottomNav />
    </div>
  );
}
