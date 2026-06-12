import { lazy, LazyExoticComponent, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import AppLayout from "./components/layout/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import PageLoader from "./components/common/PageLoader";
import Toaster from "./components/Toaster";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import { PERSIST_CACHE_KEY } from "./constants/queryConfig";
import { usePushNotifications } from "./hooks/usePushNotifications";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import FindAccountPage from "./pages/FindAccountPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";

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

export default function App() {
  const isDark = useThemeStore((s) => s.isDark);
  const checkAuth = useAuthStore((s) => s.checkAuth);
  const logout = useAuthStore((s) => s.logout);
  const queryClient = useQueryClient();
  usePushNotifications();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  useEffect(() => {
    const handleSessionExpired = () => {
      queryClient.clear();
      window.localStorage.removeItem(PERSIST_CACHE_KEY);
      logout();
    };
    window.addEventListener("growlio:session-expired", handleSessionExpired);
    return () => window.removeEventListener("growlio:session-expired", handleSessionExpired);
  }, [logout, queryClient]);

  return (
    <>
    <Toaster />
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/find-account" element={<FindAccountPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <AppLayout />
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
    </BrowserRouter>
    </>
  );
}
