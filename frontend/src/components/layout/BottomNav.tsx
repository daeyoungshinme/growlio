import { BarChart2, Home, PieChart, Wallet, Settings, TrendingUp } from "lucide-react";
import { NavLink } from "react-router-dom";

const nav = [
  { to: "/dashboard", icon: Home, label: "대시보드" },
  { to: "/portfolio", icon: PieChart, label: "포트폴리오" },
  { to: "/asset-management", icon: Wallet, label: "자산관리" },
  { to: "/invest-plan", icon: TrendingUp, label: "투자 계획" },
  { to: "/market", icon: BarChart2, label: "시장" },
  { to: "/settings", icon: Settings, label: "설정" },
];

export default function BottomNav() {
  return (
    <nav
      aria-label="하단 내비게이션"
      className="lg:hidden fixed bottom-0 inset-x-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex items-stretch justify-around z-50 pb-[env(safe-area-inset-bottom)]"
    >
      {nav.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center justify-center gap-0.5 px-2 py-3 sm:px-4 min-w-0 flex-1 text-xs font-medium transition-colors ${
              isActive
                ? "text-blue-600 dark:text-blue-400 border-t-2 border-blue-600 dark:border-blue-400 -mt-px"
                : "text-gray-500 dark:text-gray-400 border-t-2 border-transparent -mt-px"
            }`
          }
        >
          <Icon size={22} aria-hidden="true" />
          <span className="truncate max-w-full">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
