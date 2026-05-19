import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import ErrorBoundary from "./components/ErrorBoundary";
import Toaster from "./components/Toaster";
import { useAuthStore } from "./stores/authStore";
import { useThemeStore } from "./stores/themeStore";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import PortfolioPage from "./pages/PortfolioPage";
import SettingsPage from "./pages/SettingsPage";
import AssetManagementPage from "./pages/AssetManagementPage";
import InvestPlanPage from "./pages/InvestPlanPage";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  const isDark = useThemeStore((s) => s.isDark);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);

  return (
    <>
    <Toaster />
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <AppLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<ErrorBoundary><DashboardPage /></ErrorBoundary>} />
          <Route path="portfolio" element={<ErrorBoundary><PortfolioPage /></ErrorBoundary>} />
          <Route path="asset-management" element={<ErrorBoundary><AssetManagementPage /></ErrorBoundary>} />
          <Route path="invest-plan" element={<ErrorBoundary><InvestPlanPage /></ErrorBoundary>} />
          <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
          {/* 구 URL 리다이렉트 */}
          <Route path="assets" element={<Navigate to="/portfolio" replace />} />
          <Route path="trend" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
    </>
  );
}
