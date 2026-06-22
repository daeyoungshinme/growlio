import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bell, Shuffle } from "lucide-react";
import { fetchRebalancingAlerts } from "@/api/alerts";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export default function RebalancingStatusCard() {
  const { data: alertsRaw } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const { data: portfoliosRaw } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });

  const alerts = useMemo(() => (Array.isArray(alertsRaw) ? alertsRaw : []), [alertsRaw]);
  const portfolioCount = Array.isArray(portfoliosRaw) ? portfoliosRaw.length : 0;
  const alertCount = alerts.length;
  const autoCount = alerts.filter((a) => a.mode === "AUTO").length;

  if (portfolioCount === 0) return null;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-50 dark:bg-blue-950 rounded-lg">
            <Shuffle size={16} className="text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">리밸런싱 자동화</h2>
        </div>
        <Link
          to="/rebalancing"
          className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          실행하기 <ArrowRight size={12} />
        </Link>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="text-center">
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">포트폴리오</p>
          <p className="text-lg font-bold text-gray-800 dark:text-gray-200">{portfolioCount}</p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">알림 설정</p>
          <p className={`text-lg font-bold ${alertCount > 0 ? "text-blue-600 dark:text-blue-400" : "text-gray-400 dark:text-gray-500"}`}>
            {alertCount}
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">자동 실행</p>
          <p className={`text-lg font-bold ${autoCount > 0 ? "text-orange-600 dark:text-orange-400" : "text-gray-400 dark:text-gray-500"}`}>
            {autoCount}
          </p>
        </div>
      </div>

      {alertCount === 0 && (
        <Link
          to="/rebalancing?rtab=알림 설정"
          className="mt-3 flex items-center gap-2 w-full px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900 transition-colors"
        >
          <Bell size={12} />
          비중 이탈 알림 설정하기
          <ArrowRight size={12} className="ml-auto" />
        </Link>
      )}
    </div>
  );
}
