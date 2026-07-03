import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, BellOff, ChevronDown, Shuffle } from "lucide-react";

import { fetchDriftSummary } from "@/api/rebalancing";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { fetchPortfolios } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useInsights } from "@/hooks/useInsights";
import type { Insight, InsightType, InsightSeverity } from "@/api/insights";
import type { MarketSignalResponse } from "@/api/marketSignals";
import { buildCombinedStatusNote } from "@/utils/diagnosisInsights";

const SIGNAL_BG = {
  GREEN:
    "bg-blue-50 border-blue-200 text-blue-700 dark:bg-blue-950/30 dark:border-blue-800/40 dark:text-blue-300",
  YELLOW:
    "bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-950/30 dark:border-yellow-800/40 dark:text-yellow-300",
  RED: "bg-red-50 border-red-200 text-red-800 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-300",
};

const SIGNAL_LABEL = { GREEN: "안정", YELLOW: "주의", RED: "위험" };

const SIGNAL_BADGE_CLASS = {
  GREEN: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  YELLOW: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  RED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

function PortfolioDriftRow({
  summary,
  onClick,
}: {
  summary: PortfolioDriftSummary;
  onClick?: (id: string, openAlert?: boolean) => void;
}) {
  const isAlert = summary.needs_rebalancing;
  const showCompositeBadge = !isAlert && summary.has_composite_signal;
  // 구버전 API 응답(필드 없음) 호환을 위해 명시적으로 false일 때만 미설정으로 간주
  const alertNotConfigured = summary.has_alert_configured === false;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick?.(summary.portfolio_id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") onClick?.(summary.portfolio_id);
      }}
      className="w-full flex flex-col py-2.5 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/40 text-left transition-colors cursor-pointer"
    >
      <div className="flex items-center gap-2 w-full">
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${isAlert ? "bg-red-500" : "bg-green-500"}`}
        />
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1 truncate min-w-0">
          {summary.portfolio_name}
        </span>
        <span
          className={`text-xs font-semibold shrink-0 ${isAlert ? "text-red-600 dark:text-red-400" : "text-gray-400 dark:text-gray-500"}`}
        >
          최대 {summary.max_drift_pct.toFixed(1)}%
        </span>
        {isAlert && (
          <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-1.5 py-0.5 shrink-0">
            필요
          </span>
        )}
        {showCompositeBadge && (
          <span
            className="text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded-full px-1.5 py-0.5 shrink-0"
            title={summary.composite_reason ?? undefined}
          >
            점검 권장
          </span>
        )}
        {alertNotConfigured && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onClick?.(summary.portfolio_id, true);
            }}
            className="flex items-center gap-1 text-xs font-medium text-gray-400 hover:text-blue-600 dark:text-gray-500 dark:hover:text-blue-400 rounded-full px-1.5 py-0.5 shrink-0 transition-colors"
            aria-label={`${summary.portfolio_name} 알림 설정하기`}
          >
            <BellOff size={11} />
            알림 설정
          </button>
        )}
      </div>
    </div>
  );
}

function DiagnosticGauge({ value }: { value: number }) {
  const pct = Math.min(value, 100);
  const color = value >= 40 ? "#EF4444" : value >= 30 ? "#F59E0B" : "#22C55E";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
        <span>자산 집중도</span>
        <span className="font-medium">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
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
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span
        className={`mt-1.5 w-2.5 h-2.5 rounded-full shrink-0 ${severityDot[insight.severity] ?? "bg-gray-400"}`}
      />
      <div className="flex-1 min-w-0">
        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          {insight.title}
        </span>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">
          {insight.detail}
        </p>
        {insight.action_label && insight.action_url && (
          <button
            onClick={() => navigate(insight.action_url!)}
            className="mt-1.5 block py-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline active:opacity-70"
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
  onPortfolioSelect?: (id: string, openAlert?: boolean) => void;
  showAllInsights?: boolean;
  hideSignalBanner?: boolean;
  showDriftRows?: boolean;
  maxDriftRows?: number;
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

export default function RebalancingStatusCard({
  marketSignal,
  onPortfolioSelect,
  showAllInsights = false,
  hideSignalBanner = false,
  showDriftRows = false,
  maxDriftRows,
}: Props) {
  const [isOpen, setIsOpen] = useState(true);
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

  const sortedDriftSummaries = useMemo(
    () => [...(driftSummaries ?? [])].sort((a, b) => b.max_drift_pct - a.max_drift_pct),
    [driftSummaries],
  );

  const needsCount = useMemo(() => {
    if (!driftSummaries) return 0;
    return driftSummaries.filter((s) => s.needs_rebalancing).length;
  }, [driftSummaries]);

  const combinedStatusNote = useMemo(
    () => buildCombinedStatusNote(needsCount, marketSignal?.composite_level),
    [needsCount, marketSignal?.composite_level],
  );

  if (portfolioCount === 0) return null;

  const cardClass =
    needsCount > 0
      ? "card border-red-300 dark:border-red-700/60 ring-1 ring-red-200 dark:ring-red-800/40"
      : "card";

  return (
    <div className={cardClass}>
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-2 min-w-0"
          aria-expanded={isOpen}
        >
          <div className="p-1.5 bg-blue-50 dark:bg-blue-950 rounded-lg shrink-0">
            <Shuffle size={16} className="text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">투자 현황 진단</h2>
          {needsCount > 0 && (
            <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5 shrink-0">
              {needsCount}개 필요
            </span>
          )}
          <ChevronDown
            size={14}
            className={`text-gray-500 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
        <div className="flex items-center gap-1.5 shrink-0">
          {marketSignal && hideSignalBanner && (
            <span
              className={`inline-flex items-center gap-1 text-xs font-semibold rounded-full px-2 py-0.5 ${SIGNAL_BADGE_CLASS[marketSignal.composite_level]}`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
              {SIGNAL_LABEL[marketSignal.composite_level]}
            </span>
          )}
          {!showAllInsights && (
            <Link
              to="/rebalancing"
              className="flex items-center gap-1 -my-1 py-1.5 px-2 -mr-2 rounded-md text-xs text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/40 active:opacity-70 transition-colors"
            >
              분석하기 <ArrowRight size={12} />
            </Link>
          )}
        </div>
      </div>

      {isOpen && (
        <>
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

          {/* 이탈 종목 + 시장상황 결합 안내 */}
          {combinedStatusNote && (
            <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-1.5 mb-2">
              {combinedStatusNote}
            </p>
          )}

          {/* 포트폴리오별 드리프트 현황 */}
          {(showAllInsights || showDriftRows) && driftSummaries && driftSummaries.length > 0 && (
            <div className="space-y-0.5 mt-1 mb-2">
              <p className="text-xs font-medium text-gray-400 dark:text-gray-500 px-2.5 mb-1">
                포트폴리오 이탈 현황
              </p>
              {(maxDriftRows != null
                ? sortedDriftSummaries.slice(0, maxDriftRows)
                : sortedDriftSummaries
              ).map((s) => (
                <PortfolioDriftRow key={s.portfolio_id} summary={s} onClick={onPortfolioSelect} />
              ))}
            </div>
          )}

          {/* 진단 결과 섹션 */}
          {hasDiagnosis && (
            <div className="space-y-2 border-t border-gray-100 dark:border-gray-700 pt-3">
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
        </>
      )}
    </div>
  );
}
