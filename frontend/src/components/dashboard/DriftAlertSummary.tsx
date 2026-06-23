import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, Shuffle } from "lucide-react";
import { fetchDriftSummary } from "@/api/rebalancing";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export default function DriftAlertSummary() {
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

  const needsCount = useMemo(
    () => (driftSummaries ?? []).filter((s) => s.needs_rebalancing).length,
    [driftSummaries],
  );

  if (portfolioCount === 0) return null;

  const hasAlert = needsCount > 0;

  return (
    <Link
      to="/rebalancing"
      className={`card flex items-center gap-3 hover:opacity-90 transition-opacity${
        hasAlert
          ? " border-red-300 dark:border-red-700/60 ring-1 ring-red-200 dark:ring-red-800/40"
          : ""
      }`}
      aria-label="리밸런싱 현황 확인"
    >
      <div
        className={`p-2 rounded-lg shrink-0 ${hasAlert ? "bg-red-50 dark:bg-red-950/40" : "bg-blue-50 dark:bg-blue-950"}`}
      >
        {hasAlert ? (
          <AlertTriangle size={16} className="text-red-600 dark:text-red-400" aria-hidden />
        ) : (
          <CheckCircle2 size={16} className="text-blue-600 dark:text-blue-400" aria-hidden />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Shuffle size={13} className="text-gray-400 shrink-0" aria-hidden />
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">리밸런싱 현황</span>
          {hasAlert && (
            <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5">
              {needsCount}개 필요
            </span>
          )}
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {hasAlert
            ? `${needsCount}개 포트폴리오가 목표 비중에서 이탈했습니다`
            : "모든 포트폴리오가 목표 비중 내에 있습니다"}
        </p>
      </div>
      <ArrowRight size={14} className="text-gray-400 shrink-0" aria-hidden />
    </Link>
  );
}
