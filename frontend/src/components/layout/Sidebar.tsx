import { LineChart, LogOut, Moon, Sun } from "lucide-react";
import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "@/constants/nav";
import { useThemeStore } from "@/stores/themeStore";
import { useLogout } from "@/hooks/useLogout";

export default function Sidebar() {
  const logout = useLogout();
  const { isDark, toggle } = useThemeStore();

  return (
    <aside
      aria-label="사이드바 내비게이션"
      className="hidden lg:flex w-56 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 flex-col py-6 px-3"
    >
      <div className="px-3 mb-8">
        <div className="flex items-center gap-2">
          <LineChart className="text-blue-600 dark:text-blue-400" size={22} aria-hidden="true" />
          <span className="font-bold text-lg text-gray-900 dark:text-gray-50">Growlio</span>
        </div>
      </div>

      <nav aria-label="메인 메뉴" className="flex-1 space-y-1">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-50"
              }`
            }
          >
            <Icon size={18} aria-hidden="true" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="space-y-1">
        <button
          onClick={toggle}
          title={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
          aria-label={isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
        >
          {isDark ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
          {isDark ? "라이트 모드" : "다크 모드"}
        </button>
        <button
          onClick={logout}
          title="로그아웃"
          aria-label="로그아웃"
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
        >
          <LogOut size={18} aria-hidden="true" />
          로그아웃
        </button>
      </div>
    </aside>
  );
}
