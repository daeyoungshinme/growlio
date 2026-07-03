import { useMemo } from "react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { NAV_ITEMS } from "@/constants/nav";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fetchPortfolios } from "@/api/portfolios";
import { fetchDriftSummary } from "@/api/rebalancing";

export default function BottomNav() {
  const { data: portfoliosRaw } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });
  const portfolioCount = Array.isArray(portfoliosRaw) ? portfoliosRaw.length : 0;

  const { data: driftSummaries } = useQuery({
    queryKey: QUERY_KEYS.driftSummary,
    queryFn: fetchDriftSummary,
    staleTime: STALE_TIME.MEDIUM,
    enabled: portfolioCount > 0,
  });

  const needsCount = useMemo(() => {
    if (!driftSummaries) return 0;
    return driftSummaries.filter((s) => s.needs_rebalancing).length;
  }, [driftSummaries]);

  const showRebalancingBadge = portfolioCount > 0 && needsCount > 0;

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
            `flex flex-col items-center justify-center gap-0.5 px-2 py-3 sm:px-4 min-w-0 flex-1 text-xs font-medium transition-colors ${
              isActive
                ? "text-blue-600 dark:text-blue-400 border-t-2 border-blue-600 dark:border-blue-400 -mt-px"
                : "text-gray-500 dark:text-gray-400 border-t-2 border-transparent -mt-px"
            }`
          }
        >
          <div className="relative">
            <Icon size={22} aria-hidden="true" />
            {to === "/rebalancing" && showRebalancingBadge && (
              <span
                className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full"
                aria-label={`리밸런싱 필요 ${needsCount}개`}
              />
            )}
          </div>
          <span className="truncate max-w-full">{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
