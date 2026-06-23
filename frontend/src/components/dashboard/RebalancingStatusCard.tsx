import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, CheckCircle, ChevronDown, Shuffle } from "lucide-react";
import { fetchDriftSummary } from "@/api/rebalancing";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useInsights } from "@/hooks/useInsights";
import type { Insight, InsightType, InsightSeverity } from "@/api/insights";
import type { MarketSignalResponse } from "@/api/marketSignals";

const SIGNAL_BG = {
  GREEN:
    "bg-blue-50 border-blue-200 text-blue-700 dark:bg-blue-950/30 dark:border-blue-800/40 dark:text-blue-300",
  YELLOW:
    "bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-950/30 dark:border-yellow-800/40 dark:text-yellow-300",
  RED: "bg-red-50 border-red-200 text-red-800 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-300",
};

const SIGNAL_LABEL = { GREEN: "안정", YELLOW: "주의", RED: "위험" };

function DiagnosticGauge({ value }: { value: number }) {
  const pct = Math.min(value, 100);
  const color = value >= 40 ? "#EF4444" : value >= 30 ? "#F59E0B" : "#22C55E";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
        <span>자산 집중도</span>
        <span className="font-medium">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function InsightRow({ insight }: { insight: Insight }) {
  const navigate = useNavigate();
  const severityDot: Record<string, string> = {
    ALERT: "bg-red-500",
    WARNING: "bg-amber-400",
    INFO: "bg-blue-400",
  };
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${severityDot[insight.severity] ?? "bg-gray-400"}`} />
      <div className="flex-1 min-w-0">
        <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">{insight.title}</span>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">{insight.detail}</p>
        {insight.action_label && insight.action_url && (
          <button
            onClick={() => navigate(insight.action_url!)}
            className="mt-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
          >
            {insight.action_label} →
          </button>
        )}
      </div>
    </div>
  );
}

interface Props {
  marketSignal?: MarketSignalResponse | null;
  onPortfolioSelect?: (id: string) => void;
  showAllInsights?: boolean;
  hideSignalBanner?: boolean;
}

const DASHBOARD_TYPES: InsightType[] = ["CONCENTRATION", "TAX_LOSS_HARVEST"];
const ALL_INSIGHT_TYPES: InsightType[] = [
  "CONCENTRATION",
  "UNDERPERFORMANCE",
  "HIGH_COST",
  "TAX_LOSS_HARVEST",
  "DEPOSIT_SHORTFALL",
];
const SEVERITY_ORDER: Record<InsightSeverity, number> = { ALERT: 0, WARNING: 1, INFO: 2 };

export default function RebalancingStatusCard({ marketSignal, onPortfolioSelect, showAllInsights = false, hideSignalBanner = false }: Props) {
  const [isOpen, setIsOpen] = useState(true);
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

  const { data: allInsights } = useInsights();
  const diagInsights = useMemo(() => {
    const types = showAllInsights ? ALL_INSIGHT_TYPES : DASHBOARD_TYPES;
    return [...(allInsights ?? [])]
      .filter((i) => types.includes(i.type))
      .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3));
  }, [allInsights, showAllInsights]);
  const concentrationInsight = diagInsights.find((i) => i.type === "CONCENTRATION");
  const otherInsights = diagInsights.filter((i) => i.type !== "CONCENTRATION");
  const hasDiagnosis = diagInsights.length > 0;

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

  const cardClass = needsCount > 0
    ? "card border-red-300 dark:border-red-700/60 ring-1 ring-red-200 dark:ring-red-800/40"
    : "card";

  return (
    <div className={cardClass}>
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-2"
          aria-expanded={isOpen}
        >
          <div className="p-1.5 bg-blue-50 dark:bg-blue-950 rounded-lg">
            <Shuffle size={16} className="text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            투자 현황 진단
          </h2>
          {needsCount > 0 && (
            <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5">
              {needsCount}개 필요
            </span>
          )}
          <ChevronDown
            size={14}
            className={`text-gray-500 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
        {!showAllInsights && (
          <Link
            to="/rebalancing"
            className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline"
          >
            분석하기 <ArrowRight size={12} />
          </Link>
        )}
      </div>

      {isOpen && <>
      {/* 시장 신호 배너 */}
      {marketSignal && !hideSignalBanner && (
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

      {/* 진단 결과 섹션 */}
      {hasDiagnosis && (
        <div className="mb-3 space-y-2">
          <p className="text-xs font-medium text-gray-400 dark:text-gray-500">진단 결과</p>
          {concentrationInsight?.metric_value != null && (
            <DiagnosticGauge value={concentrationInsight.metric_value} />
          )}
          {concentrationInsight && concentrationInsight.metric_value == null && (
            <InsightRow insight={concentrationInsight} />
          )}
          {otherInsights.map((insight, idx) => (
            <InsightRow key={`insight-${idx}`} insight={insight} />
          ))}
        </div>
      )}

      {/* 리밸런싱 현황 목록 */}
      <div>
        <p className="text-xs font-medium text-gray-400 dark:text-gray-500 mb-2">리밸런싱 현황</p>
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
              const itemClass =
                "flex items-center justify-between gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800/60 hover:bg-gray-100 dark:hover:bg-gray-700/60 transition-colors w-full text-left";
              const innerContent = (
                <>
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
                </>
              );
              return onPortfolioSelect ? (
                <button
                  key={s.portfolio_id}
                  onClick={() => onPortfolioSelect(s.portfolio_id)}
                  className={itemClass}
                >
                  {innerContent}
                </button>
              ) : (
                <Link
                  key={s.portfolio_id}
                  to={`/rebalancing?portfolioId=${s.portfolio_id}`}
                  className={itemClass}
                >
                  {innerContent}
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {!isLoading && needsCount === 0 && sorted.length > 0 && (
        <div className="flex items-center gap-1.5 mt-2 text-xs text-green-600 dark:text-green-400">
          <CheckCircle size={13} />
          모든 포트폴리오가 목표 비중을 유지하고 있습니다
        </div>
      )}
      </>}
    </div>
  );
}
