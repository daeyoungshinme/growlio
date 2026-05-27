import { Home, PieChart, Wallet, TrendingUp, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

const nav = [
  { to: "/dashboard", icon: Home, label: "대시보드" },
  { to: "/portfolio", icon: PieChart, label: "포트폴리오" },
  { to: "/asset-management", icon: Wallet, label: "자산관리" },
  { to: "/invest-plan", icon: TrendingUp, label: "투자 계획" },
  { to: "/settings", icon: Settings, label: "설정" },
];

export default function BottomNav() {
  return (
    <nav
      aria-label="하단 내비게이션"
      className="lg:hidden fixed bottom-0 inset-x-0 h-16 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex items-center justify-around z-50"
    >
      {nav.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 px-2 py-1 rounded-lg text-xs font-medium transition-colors ${
              isActive
                ? "text-blue-600 dark:text-blue-400"
                : "text-gray-500 dark:text-gray-400"
            }`
          }
        >
          <Icon size={20} aria-hidden="true" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
