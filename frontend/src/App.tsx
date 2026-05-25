import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import PageLoader from "./components/common/PageLoader";
import Toaster from "./components/Toaster";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import FindAccountPage from "./pages/FindAccountPage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";

const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const PortfolioPage = lazy(() => import("./pages/PortfolioPage"));
const AssetManagementPage = lazy(() => import("./pages/AssetManagementPage"));
const InvestPlanPage = lazy(() => import("./pages/InvestPlanPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isAuthChecking = useAuthStore((s) => s.isAuthChecking);
  if (isAuthChecking) return <PageLoader />;
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  const isDark = useThemeStore((s) => s.isDark);
  const checkAuth = useAuthStore((s) => s.checkAuth);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

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
          <Route path="dashboard" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><DashboardPage /></Suspense></ErrorBoundary>} />
          <Route path="portfolio" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><PortfolioPage /></Suspense></ErrorBoundary>} />
          <Route path="asset-management" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><AssetManagementPage /></Suspense></ErrorBoundary>} />
          <Route path="invest-plan" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><InvestPlanPage /></Suspense></ErrorBoundary>} />
          <Route path="settings" element={<ErrorBoundary><Suspense fallback={<PageLoader />}><SettingsPage /></Suspense></ErrorBoundary>} />
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
