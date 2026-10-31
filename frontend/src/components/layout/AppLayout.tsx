import { useCallback, useEffect, useRef } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import { App } from "@capacitor/app";
import Sidebar from "./Sidebar";
import BottomNav from "./BottomNav";
import OfflineBanner from "@/components/common/OfflineBanner";
import { useAuthStore } from "@/stores/authStore";
import { toast } from "@/utils/toast";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { useSwipeNavigation } from "@/hooks/useSwipeNavigation";
import { useRevealFocusedInput } from "@/hooks/useRevealFocusedInput";
import { useLatestRef } from "@/hooks/useLatestRef";
import { hasOpenModal } from "@/hooks/useModalBehavior";
import { ExchangeRateProvider } from "@/context/ExchangeRateContext";
import { isNativePlatform } from "@/utils/platform";
import { RefreshContext } from "./RefreshContext";

export default function AppLayout() {
  const needsPasswordReset = useAuthStore((s) => s.needsPasswordReset);
  const email = useAuthStore((s) => s.email);
  const forgotPassword = useAuthStore((s) => s.forgotPassword);
  const navigate = useNavigate();
  const navigateRef = useLatestRef(navigate);

  const mainRef = useRef<HTMLElement>(null);
  const refreshFnRef = useRef<(() => Promise<void>) | null>(null);

  const registerRefresh = useCallback((fn: (() => Promise<void>) | null) => {
    refreshFnRef.current = fn;
  }, []);

  const { isPulling, pullDistance, isRefreshing } = usePullToRefresh({
    onRefresh: async () => {
      if (refreshFnRef.current) await refreshFnRef.current();
    },
    containerRef: mainRef,
  });

  // 모바일에서만 스와이프 탭 전환 (lg 이상은 Sidebar 사용)
  useSwipeNavigation(mainRef);

  // 키보드에 가린 입력을 끌어올린다 (AndroidManifest adjustResize와 함께, plans/102 E3)
  useRevealFocusedInput();

  // Android 물리 뒤로가기 버튼 처리 — navigate는 경로마다 바뀌므로 ref로 읽어 리스너를 한 번만 등록한다
  // (deps에 넣으면 이동마다 재등록되고, 비동기 해제 사이에 리스너가 겹쳐 뒤로가기가 두 번 될 수 있다)
  useEffect(() => {
    if (!isNativePlatform()) return;
    const handle = App.addListener("backButton", ({ canGoBack }) => {
      // 모달이 열려 있으면 Escape 이벤트로 닫기
      if (hasOpenModal()) {
        document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
        return;
      }
      if (canGoBack) {
        void navigateRef.current(-1);
      } else {
        void App.exitApp();
      }
    });
    return () => {
      void handle.then((h) => h.remove());
    };
  }, [navigateRef]);

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
    <ExchangeRateProvider>
      <RefreshContext.Provider value={{ registerRefresh }}>
        {/* h-dvh: 모바일 주소창을 뺀 실제 높이(미지원 WebView는 h-screen 규칙이 남는다). 상단 safe-area는
            Android 15+ edge-to-edge에서 상태바와 겹치지 않게(그 외 환경은 0) — plans/79 F */}
        <div className="flex h-screen h-dvh pt-[env(safe-area-inset-top)] bg-gray-50 dark:bg-gray-950">
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
            <OfflineBanner />
            {/* Pull-to-Refresh 인디케이터 */}
            {(isPulling || isRefreshing) && (
              <div
                className="absolute top-[env(safe-area-inset-top)] left-0 right-0 z-50 flex items-center justify-center pointer-events-none lg:hidden"
                style={{ height: `${Math.max(pullDistance, isRefreshing ? 40 : 0)}px` }}
              >
                <div
                  className={`w-7 h-7 rounded-full border-2 border-blue-500 border-t-transparent ${
                    isRefreshing ? "animate-spin" : ""
                  }`}
                  style={
                    !isRefreshing
                      ? {
                          transform: `rotate(${(pullDistance / 60) * 270}deg)`,
                          opacity: pullDistance / 60,
                        }
                      : {}
                  }
                />
              </div>
            )}
            <main
              ref={mainRef}
              className="flex-1 overflow-auto overscroll-y-contain px-3 py-4 pb-[calc(var(--bottom-nav-h)+0.5rem+env(safe-area-inset-bottom))] lg:p-6 lg:pb-6"
              style={
                isPulling
                  ? { transform: `translateY(${pullDistance}px)`, transition: "none" }
                  : { transition: "transform 0.2s ease" }
              }
            >
              <Outlet />
            </main>
          </div>
          <BottomNav />
        </div>
      </RefreshContext.Provider>
    </ExchangeRateProvider>
  );
}
