import type { ReactNode } from "react";

/** AppLayout 밖의 전체 화면(로그인·가입·재설정·딥링크 확인 등) 셸.
 * edge-to-edge Android에서 상태바·제스처바에 카드가 겹치지 않게 safe-area를 비우고,
 * 주소창이 줄어드는 모바일 브라우저에서도 높이가 맞도록 dvh를 쓴다. */
export default function AuthLayout({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className="min-h-screen min-h-dvh flex flex-col bg-gray-50 dark:bg-gray-950 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)]">
      <div className={`flex-1 flex items-center justify-center px-4 ${className}`}>{children}</div>
    </div>
  );
}
