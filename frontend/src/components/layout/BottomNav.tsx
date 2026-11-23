import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "@/constants/nav";
import { navBadgeLabel, useNavBadges } from "@/hooks/useNavBadges";

export default function BottomNav() {
  const badges = useNavBadges();

  return (
    <nav
      aria-label="하단 내비게이션"
      className="lg:hidden fixed bottom-0 inset-x-0 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700 flex items-stretch justify-around z-50 pb-[env(safe-area-inset-bottom)]"
    >
      {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex flex-col items-center justify-center gap-0.5 px-2 h-(--bottom-nav-h) sm:px-4 min-w-0 flex-1 text-xs font-medium transition-colors ${
              isActive
                ? "text-blue-600 dark:text-blue-400 border-t-2 border-blue-600 dark:border-blue-400 -mt-px"
                : "text-gray-500 dark:text-gray-400 border-t-2 border-transparent -mt-px"
            }`
          }
        >
          <div className="relative">
            <Icon size={22} aria-hidden="true" />
            {navBadgeLabel(to, badges) && (
              <span
                className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full"
                aria-label={navBadgeLabel(to, badges) ?? undefined}
              />
            )}
          </div>
          <span className="truncate max-w-full">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
