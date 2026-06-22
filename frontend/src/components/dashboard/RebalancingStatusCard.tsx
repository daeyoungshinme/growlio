import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, CheckCircle, Shuffle } from "lucide-react";
import { fetchDriftSummary } from "@/api/rebalancing";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import type { MarketSignalResponse } from "@/api/marketSignals";

const SIGNAL_BG = {
  GREEN:
    "bg-blue-50 border-blue-200 text-blue-700 dark:bg-blue-950/30 dark:border-blue-800/40 dark:text-blue-300",
  YELLOW:
    "bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-950/30 dark:border-yellow-800/40 dark:text-yellow-300",
  RED: "bg-red-50 border-red-200 text-red-800 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-300",
};

const SIGNAL_LABEL = { GREEN: "안정", YELLOW: "주의", RED: "위험" };

interface Props {
  marketSignal?: MarketSignalResponse | null;
}

export default function RebalancingStatusCard({ marketSignal }: Props) {
  const { data: portfoliosRaw } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });
  const portfolioCount = Array.isArray(portfoliosRaw) ? portfoliosRaw.length : 0;

  const { data: driftSummaries, isLoading } = useQuery({
    queryKey: QUERY_KEYS.driftSummary,
    queryFn: fetchDriftSummary,
    staleTime: STALE_TIME.MEDIUM,
    enabled: portfolioCount > 0,
  });

  const sorted = useMemo(() => {
    if (!driftSummaries) return [];
    return [...driftSummaries].sort((a, b) => {
      if (a.needs_rebalancing !== b.needs_rebalancing)
        return a.needs_rebalancing ? -1 : 1;
      return b.max_drift_pct - a.max_drift_pct;
    });
  }, [driftSummaries]);

  const needsCount = sorted.filter((s) => s.needs_rebalancing).length;

  if (portfolioCount === 0) return null;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-blue-50 dark:bg-blue-950 rounded-lg">
            <Shuffle size={16} className="text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            리밸런싱 현황
          </h2>
          {needsCount > 0 && (
            <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5">
              {needsCount}개 필요
            </span>
          )}
        </div>
        <Link
          to="/rebalancing"
          className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          분석하기 <ArrowRight size={12} />
        </Link>
      </div>

      {marketSignal && (
        <Link
          to="/rebalancing"
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium mb-3 transition-colors ${SIGNAL_BG[marketSignal.composite_level]}`}
        >
          {marketSignal.composite_level === "GREEN" ? (
            <Activity size={13} className="flex-shrink-0" />
          ) : (
            <AlertTriangle size={13} className="flex-shrink-0" />
          )}
          <span>
            시장 신호:{" "}
            <span className="font-bold">{SIGNAL_LABEL[marketSignal.composite_level]}</span>
            {marketSignal.composite_level !== "GREEN" && " — 리밸런싱 전략을 확인하세요"}
          </span>
          <ArrowRight size={12} className="ml-auto flex-shrink-0" />
        </Link>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-10 bg-gray-100 dark:bg-gray-700 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <div className="flex flex-col gap-2 py-2">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            리밸런싱 포트폴리오에 목표 계좌를 지정하면 현황이 표시됩니다.
          </p>
          <Link
            to="/rebalancing"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline inline-flex items-center gap-1"
          >
            계좌 지정하러 가기 <ArrowRight size={11} />
          </Link>
        </div>
      ) : (
        <div className="space-y-1.5">
          {sorted.map((s) => {
            const isNeeded = s.needs_rebalancing;
            const isCaution = !isNeeded && s.max_drift_pct >= s.threshold_pct / 2;
            return (
              <Link
                key={s.portfolio_id}
                to={`/rebalancing?portfolio=${s.portfolio_id}`}
                className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800/60 hover:bg-gray-100 dark:hover:bg-gray-700/60 transition-colors"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {isNeeded ? (
                    <AlertTriangle size={13} className="text-red-500 shrink-0" />
                  ) : isCaution ? (
                    <AlertTriangle size={13} className="text-amber-400 shrink-0" />
                  ) : (
                    <CheckCircle size={13} className="text-green-500 shrink-0" />
                  )}
                  <span className="text-xs font-medium text-gray-700 dark:text-gray-300 truncate">
                    {s.portfolio_name}
                  </span>
                  {/* 상위 이탈 종목 chip */}
                  {isNeeded && s.top_drifted_items[0] && (
                    <span className="hidden sm:inline text-xs text-gray-400 dark:text-gray-500 shrink-0">
                      {s.top_drifted_items[0].name}{" "}
                      <span className={s.top_drifted_items[0].weight_diff_pct > 0 ? "text-red-500" : "text-blue-500"}>
                        {s.top_drifted_items[0].weight_diff_pct > 0 ? "▲" : "▼"}
                        {Math.abs(s.top_drifted_items[0].weight_diff_pct).toFixed(1)}%
                      </span>
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {isNeeded ? (
                    <span className="text-xs text-red-500 dark:text-red-400 font-medium">
                      최대 {s.max_drift_pct.toFixed(1)}% 이탈
                    </span>
                  ) : isCaution ? (
                    <span className="text-xs text-amber-500 dark:text-amber-400 font-medium">
                      {s.max_drift_pct.toFixed(1)}% 이탈
                    </span>
                  ) : (
                    <span className="text-xs text-green-600 dark:text-green-400 font-medium">안정</span>
                  )}
                  <ArrowRight size={11} className="text-gray-400" />
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {!isLoading && needsCount === 0 && sorted.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-green-600 dark:text-green-400">
          <CheckCircle size={13} />
          모든 포트폴리오가 목표 비중을 유지하고 있습니다
        </div>
      )}
    </div>
  );
}
