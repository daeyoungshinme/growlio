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
import { PERSIST_CACHE_KEY } from "./constants/queryConfig";
import { usePushNotifications } from "./hooks/usePushNotifications";
import { useWidget } from "./hooks/useWidget";
import { useMainPageFetching } from "./hooks/usePortfolioTabFetching";
import BiometricGuard from "./components/common/BiometricGuard";
import { fetchDashboard } from "./api/dashboard";
import { fetchAccounts, fetchExchangeRate } from "./api/assets";
import { fetchPortfolioOverviewLite } from "./api/portfolios";
import { fetchDCAAnalysis } from "./api/invest";
import { QUERY_KEYS } from "./constants/queryKeys";
const LoginPage = lazy(() => import("./pages/LoginPage"));
const RegisterPage = lazy(() => import("./pages/RegisterPage"));
const FindAccountPage = lazy(() => import("./pages/FindAccountPage"));
const ForgotPasswordPage = lazy(() => import("./pages/ForgotPasswordPage"));
const ResetPasswordPage = lazy(() => import("./pages/ResetPasswordPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const PortfolioPage = lazy(() => import("./pages/PortfolioPage"));
const AssetManagementPage = lazy(() => import("./pages/AssetManagementPage"));
const InvestPlanPage = lazy(() => import("./pages/InvestPlanPage"));
const MarketPage = lazy(() => import("./pages/MarketPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

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

function AppRoutes() {
  const isAuthChecking = useAuthStore((s) => s.isAuthChecking);
  const isPageLoading = useMainPageFetching();

  return (
    <>
      <TopLoadingBar isVisible={isAuthChecking || isPageLoading} />
      <Routes>
        <Route path="/login" element={<LazyRoute Component={LoginPage} />} />
        <Route path="/register" element={<LazyRoute Component={RegisterPage} />} />
        <Route path="/find-account" element={<LazyRoute Component={FindAccountPage} />} />
        <Route path="/forgot-password" element={<LazyRoute Component={ForgotPasswordPage} />} />
        <Route path="/reset-password" element={<LazyRoute Component={ResetPasswordPage} />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <BiometricGuard>
                <AppLayout />
              </BiometricGuard>
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<LazyRoute Component={DashboardPage} />} />
          <Route path="portfolio" element={<LazyRoute Component={PortfolioPage} />} />
          <Route path="asset-management" element={<LazyRoute Component={AssetManagementPage} />} />
          <Route path="invest-plan" element={<LazyRoute Component={InvestPlanPage} />} />
          <Route path="market" element={<LazyRoute Component={MarketPage} />} />
          <Route path="settings" element={<LazyRoute Component={SettingsPage} />} />
          {/* 구 URL 리다이렉트 */}
          <Route path="assets" element={<Navigate to="/portfolio" replace />} />
          <Route path="trend" element={<Navigate to="/dashboard" replace />} />
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
  usePushNotifications();
  useWidget();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  const prefetchDashboardData = useCallback(() => {
    queryClient.prefetchQuery({ queryKey: QUERY_KEYS.dashboard, queryFn: fetchDashboard });
    queryClient.prefetchQuery({ queryKey: QUERY_KEYS.accounts, queryFn: fetchAccounts });
    queryClient.prefetchQuery({
      queryKey: QUERY_KEYS.portfolioOverviewLite,
      queryFn: fetchPortfolioOverviewLite,
    });
    queryClient.prefetchQuery({ queryKey: QUERY_KEYS.dcaAnalysis, queryFn: fetchDCAAnalysis });
    queryClient.prefetchQuery({ queryKey: QUERY_KEYS.exchangeRate, queryFn: fetchExchangeRate });
    import("./pages/DashboardPage").catch(() => {});
  }, [queryClient]);

  useEffect(() => {
    // 세션이 감지되는 순간(localStorage, 네트워크 전) prefetch를 /auth/me와 병렬 실행
    checkAuth(prefetchDashboardData);
  }, [checkAuth, prefetchDashboardData]);

  useEffect(() => {
    const handleSessionExpired = () => {
      queryClient.clear();
      window.localStorage.removeItem(PERSIST_CACHE_KEY);
      window.localStorage.removeItem(AUTH_ME_CACHE_KEY);
      logout();
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
