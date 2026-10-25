import { lazy, LazyExoticComponent, Suspense, useCallback, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import AppLayout from "./components/layout/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import PageLoader from "./components/common/PageLoader";
import TopLoadingBar from "./components/common/TopLoadingBar";
import Toaster from "./components/Toaster";
import { useAuthStore, AUTH_ME_CACHE_KEY } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import { usePushNotifications } from "./hooks/usePushNotifications";
import { useSyncAllWatcher } from "./hooks/useSyncAllWatcher";
import { useWidget } from "./hooks/useWidget";
import { useMainPageFetching } from "./hooks/usePortfolioTabFetching";
import BiometricGuard from "./components/common/BiometricGuard";
import { fetchDashboard } from "./api/dashboard";
import { fetchAccounts, fetchExchangeRate } from "./api/assets";
import { fetchPortfolioOverviewLite } from "./api/portfolios";
import { fetchDCAAnalysis } from "./api/invest";
import { fetchSettings } from "./api/settings";
import { QUERY_KEYS } from "./constants/queryKeys";
import { storageRemove } from "./utils/safeStorage";

const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const FindAccountPage = lazy(() => import("./pages/FindAccountPage"));
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"));
const AuthCallbackPage = lazy(() => import("./pages/AuthCallbackPage"));
const RebalancingPlanConfirmPage = lazy(() => import("./pages/RebalancingPlanConfirmPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const AssetsPage = lazy(() => import("./pages/AssetsPage"));
const InvestPlanPage = lazy(() => import("./pages/InvestPlanPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const NotificationSettingsPage = lazy(() => import("./pages/NotificationSettingsPage"));
const RebalancingPage = lazy(() => import("./pages/RebalancingPage"));

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isAuthChecking = useAuthStore((s) => s.isAuthChecking);
  if (isAuthChecking) return <PageLoader />;
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function LazyRoute({ Component }: { Component: LazyExoticComponent<() => React.JSX.Element> }) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<PageLoader />}>
        <Component />
      </Suspense>
    </ErrorBoundary>
  );
}

/** 로딩 바 전용 leaf — useIsFetching 카운트가 바뀔 때마다 리렌더되므로 라우트 트리와 분리한다
 * (AppRoutes에 두면 로드 버스트·폴링 때마다 현재 페이지 전체가 다시 렌더됐다) */
function AppTopLoadingBar() {
  const isAuthChecking = useAuthStore((s) => s.isAuthChecking);
  const isPageLoading = useMainPageFetching();
  return <TopLoadingBar isVisible={isAuthChecking || isPageLoading} />;
}

function AppRoutes() {
  usePushNotifications();
  useSyncAllWatcher();

  return (
    <>
      <AppTopLoadingBar />
      <Routes>
        <Route path="/login" element={<LazyRoute Component={LoginPage} />} />
        <Route path="/register" element={<LazyRoute Component={RegisterPage} />} />
        <Route path="/find-account" element={<LazyRoute Component={FindAccountPage} />} />
        <Route path="/forgot-password" element={<LazyRoute Component={ForgotPasswordPage} />} />
        <Route path="/reset-password" element={<LazyRoute Component={ResetPasswordPage} />} />
        <Route path="/auth/callback" element={<LazyRoute Component={AuthCallbackPage} />} />
        <Route
          path="/rebalancing/plan-confirm"
          element={<LazyRoute Component={RebalancingPlanConfirmPage} />}
        />
        <Route
          path="/"
          element={
            <ErrorBoundary>
              <PrivateRoute>
                <BiometricGuard>
                  <AppLayout />
                </BiometricGuard>
              </PrivateRoute>
            </ErrorBoundary>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<LazyRoute Component={DashboardPage} />} />
          <Route path="assets" element={<LazyRoute Component={AssetsPage} />} />
          <Route path="invest-plan" element={<LazyRoute Component={InvestPlanPage} />} />
          <Route path="settings" element={<LazyRoute Component={SettingsPage} />} />
          <Route
            path="settings/notifications"
            element={<LazyRoute Component={NotificationSettingsPage} />}
          />
          <Route path="rebalancing" element={<LazyRoute Component={RebalancingPage} />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  const isDark = useThemeStore((s) => s.isDark);
  const checkAuth = useAuthStore((s) => s.checkAuth);
  const logout = useAuthStore((s) => s.logout);
  const queryClient = useQueryClient();
  useWidget();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  const prefetchDashboardData = useCallback(() => {
    void queryClient.prefetchQuery({ queryKey: QUERY_KEYS.dashboard, queryFn: fetchDashboard });
    void queryClient.prefetchQuery({ queryKey: QUERY_KEYS.accounts, queryFn: fetchAccounts });
    void queryClient.prefetchQuery({
      queryKey: QUERY_KEYS.portfolioOverviewLite,
      queryFn: fetchPortfolioOverviewLite,
    });
    void queryClient.prefetchQuery({ queryKey: QUERY_KEYS.dcaAnalysis, queryFn: fetchDCAAnalysis });
    void queryClient.prefetchQuery({
      queryKey: QUERY_KEYS.exchangeRate,
      queryFn: fetchExchangeRate,
    });
    void queryClient.prefetchQuery({ queryKey: QUERY_KEYS.settings, queryFn: fetchSettings });
    import("./pages/DashboardPage").catch(() => {});
  }, [queryClient]);

  useEffect(() => {
    // 세션이 감지되는 순간(localStorage, 네트워크 전) prefetch를 /auth/me와 병렬 실행
    void checkAuth(prefetchDashboardData);
  }, [checkAuth, prefetchDashboardData]);

  useEffect(() => {
    const handleSessionExpired = () => {
      // clear()의 제거 이벤트를 persister가 받아 빈 상태를 다시 저장하므로(2s throttle) persist 캐시도
      // 사실상 비워진다 — 공용 기기에서 다음 사용자에게 이전 데이터가 보이지 않는 쪽이라 의도대로 둔다.
      // 저장소 키 자체 삭제는 명시적 로그아웃(useLogout.ts)·탈퇴에서 한다.
      queryClient.clear();
      storageRemove(AUTH_ME_CACHE_KEY);
      void logout();
    };
    window.addEventListener("growlio:session-expired", handleSessionExpired);
    return () => window.removeEventListener("growlio:session-expired", handleSessionExpired);
  }, [logout, queryClient]);

  return (
    <>
      <Toaster />
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </>
  );
}
