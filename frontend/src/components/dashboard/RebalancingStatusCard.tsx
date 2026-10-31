import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BellOff, ChevronDown, Shuffle } from "lucide-react";

import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { useInsights } from "@/hooks/useInsights";
import { useCollapsible } from "@/hooks/useCollapsible";
import type { Insight, InsightType, InsightSeverity } from "@/api/insights";
import type { MarketSignalResponse } from "@/api/marketSignals";
import { buildCombinedStatusNote } from "@/utils/diagnosisInsights";
import { DRIFT_STATUS_LABEL, getDriftStatus } from "@/utils/portfolio";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import { TOUCH_TARGET_MIN_MOBILE_ONLY, TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { driftSummaryQuery, portfoliosQuery } from "@/api/queryOptions";

const OTHER_INSIGHTS_VISIBLE_LIMIT = 3;

function PortfolioDriftRow({
  summary,
  onClick,
}: {
  summary: PortfolioDriftSummary;
  onClick?: (id: string, openAlert?: boolean) => void;
}) {
  const isAlert = summary.needs_rebalancing;
  // 포트폴리오 카드·분석 진단 카드와 같은 3단계 — 절반 이상 이탈이면 "주의"(plans/63 P1-2)
  const isCaution =
    !isAlert && getDriftStatus(summary.max_drift_pct, summary.threshold_pct) === "caution";
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
          className={`w-2 h-2 rounded-full shrink-0 ${isAlert ? "bg-red-500" : isCaution ? "bg-amber-500" : "bg-green-500"}`}
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
            {DRIFT_STATUS_LABEL.critical}
          </span>
        )}
        {showCompositeBadge && (
          <span className="text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded-full px-1.5 py-0.5 shrink-0">
            점검 권장
          </span>
        )}
        {alertNotConfigured && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onClick?.(summary.portfolio_id, true);
            }}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} gap-1 text-xs font-medium text-gray-400 hover:text-blue-600 dark:text-gray-500 dark:hover:text-blue-400 rounded-full px-1.5 py-0.5 shrink-0 transition-colors`}
            aria-label={`${summary.portfolio_name} 자동화 설정하기`}
          >
            <BellOff size={11} />
            자동화 설정
          </button>
        )}
      </div>
      {/* 점검 권장 사유 — title은 터치에서 안 보이므로 화면에 표시 (docs/plans/67) */}
      {showCompositeBadge && summary.composite_reason && (
        <p className="text-xs text-amber-700 dark:text-amber-400 mt-1 pl-4">
          {summary.composite_reason}
        </p>
      )}
    </div>
  );
}

function DiagnosticGauge({ value }: { value: number }) {
  const pct = Math.min(value, 100);
  const color = value >= 40 ? "#EF4444" : value >= 30 ? "#F59E0B" : "#22C55E";
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
        {/* 같은 진단 탭의 위험 지표 "최대 종목 비중"(단일 종목)과 다른 값 — 주식·예금 등 가장 큰 자산 유형의
            비중임을 라벨로 구분한다(plans/63 P2-1) */}
        <span>자산 유형 집중도 (가장 큰 유형 비중)</span>
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
  const actionUrl = insight.action_url;
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
        {insight.action_label && actionUrl && (
          <button
            onClick={() => navigate(actionUrl)}
            className={`${TOUCH_TARGET_ROW} text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline active:opacity-70`}
          >
            {insight.action_label} →
          </button>
        )}
      </div>
    </div>
  );
}

/** 리밸런싱 › 진단 탭 상단 카드 — 포트폴리오별 이탈 현황 + 전체 자산 진단. 시장 신호 표시는 탭의
 * MarketSignalBanner가 맡고, 여기서는 이탈과 결합한 안내 문구에만 쓴다(홈 인스턴스는 plans/50에서 제거). */
interface Props {
  marketSignal?: MarketSignalResponse | null;
  onPortfolioSelect?: (id: string, openAlert?: boolean) => void;
  /** 지정 시, 포트폴리오가 하나도 없을 때 `null` 대신 "포트폴리오 만들기" CTA 카드를 렌더한다.
   * 리밸런싱 진단 탭 전용(대시보드 인스턴스는 미지정 → 종전대로 아무것도 렌더하지 않음). */
  emptyStateCta?: () => void;
}

// 리밸런싱 기회는 이 카드의 포트폴리오 이탈 행(drift-summary)이 따로 보여 주므로 뺀다
const ALL_INSIGHT_TYPES: InsightType[] = ["CONCENTRATION", "TAX_LOSS_HARVEST"];
const SEVERITY_ORDER: Record<InsightSeverity, number> = { ALERT: 0, WARNING: 1, INFO: 2 };

export default function RebalancingStatusCard({
  marketSignal,
  onPortfolioSelect,
  emptyStateCta,
}: Props) {
  const [isOpen, toggleOpen] = useCollapsible(true);
  const [showAllOtherInsights, toggleShowAllOtherInsights] = useCollapsible(false);
  const {
    data: portfoliosRaw,
    isLoading: portfoliosLoading,
    isError: portfoliosError,
    refetch: refetchPortfolios,
  } = useQuery(portfoliosQuery);
  const portfolioCount = Array.isArray(portfoliosRaw) ? portfoliosRaw.length : 0;

  // /drift-summary는 백엔드에서 자체적으로 포트폴리오 목록을 조회하므로(빈 목록이면 [] 반환),
  // 프론트의 portfolios 쿼리 완료를 기다릴 필요 없이 독립적으로 즉시 발화한다.
  const { data: driftSummaries } = useQuery(driftSummaryQuery);

  const { data: allInsights } = useInsights();
  const diagInsights = useMemo(() => {
    return [...(allInsights ?? [])]
      .filter((i) => ALL_INSIGHT_TYPES.includes(i.type))
      .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3));
  }, [allInsights]);
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

  if (portfoliosLoading) {
    return <SkeletonCard />;
  }

  if (portfoliosError) {
    if (!emptyStateCta) return null;
    return (
      <div className="card">
        <div className="flex items-center justify-between gap-2 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 rounded-lg px-3 py-2">
          <span>포트폴리오 현황을 불러오지 못했습니다.</span>
          <button
            onClick={() => refetchPortfolios()}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-none gap-1 font-medium hover:text-red-600 dark:hover:text-red-300 transition-colors`}
          >
            다시 시도
          </button>
        </div>
      </div>
    );
  }

  if (portfolioCount === 0) {
    if (!emptyStateCta) return null;
    return (
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <div className="p-1.5 bg-blue-50 dark:bg-blue-950 rounded-lg shrink-0">
            <Shuffle size={16} className="text-blue-600 dark:text-blue-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">리밸런싱 점검</h2>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          아직 등록된 포트폴리오가 없어 진단할 수 없습니다. 포트폴리오를 만들면 목표 비중 대비 이탈
          현황과 시장 상황을 여기서 확인할 수 있습니다.
        </p>
        <button
          onClick={emptyStateCta}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} !justify-start gap-1 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline`}
        >
          포트폴리오 만들기 <ArrowRight size={12} />
        </button>
      </div>
    );
  }

  const cardClass =
    needsCount > 0
      ? "card border-red-300 dark:border-red-700/60 ring-1 ring-red-200 dark:ring-red-800/40"
      : "card";

  return (
    <CollapsibleCard
      icon={Shuffle}
      iconWrapClassName="bg-blue-50 dark:bg-blue-950"
      iconColorClassName="text-blue-600 dark:text-blue-400"
      title="리밸런싱 점검"
      titleBadge={
        needsCount > 0 ? (
          <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5 shrink-0">
            {needsCount}개 필요
          </span>
        ) : undefined
      }
      isOpen={isOpen}
      onToggle={toggleOpen}
      cardClassName={cardClass}
    >
      {/* 이탈 종목 + 시장상황 결합 안내 */}
      {combinedStatusNote && (
        <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-1.5 mb-2">
          {combinedStatusNote}
        </p>
      )}

      {/* 포트폴리오별 드리프트 현황 */}
      {driftSummaries && driftSummaries.length > 0 && (
        <div className="space-y-0.5 mt-1 mb-2">
          <p className="text-xs font-medium text-gray-400 dark:text-gray-500 px-2.5 mb-1">
            포트폴리오 이탈 현황
          </p>
          {sortedDriftSummaries.map((s) => (
            <PortfolioDriftRow key={s.portfolio_id} summary={s} onClick={onPortfolioSelect} />
          ))}
        </div>
      )}

      {/* 진단 결과 섹션 */}
      {hasDiagnosis && (
        <div className="space-y-2 border-t border-gray-100 dark:border-gray-700 pt-3">
          {/* 전체 자산 기준(insights API) — 포트폴리오 탭의 "이 포트폴리오 진단"과 구분(plans/64 S4) */}
          <p className="text-xs font-medium text-gray-400 dark:text-gray-500">전체 자산 진단</p>
          {concentrationInsight?.metric_value != null && (
            <DiagnosticGauge value={concentrationInsight.metric_value} />
          )}
          {concentrationInsight && concentrationInsight.metric_value == null && (
            <InsightRow insight={concentrationInsight} />
          )}
          {(showAllOtherInsights
            ? otherInsights
            : otherInsights.slice(0, OTHER_INSIGHTS_VISIBLE_LIMIT)
          ).map((insight, idx) => (
            <InsightRow key={`insight-${idx}`} insight={insight} />
          ))}
          {otherInsights.length > OTHER_INSIGHTS_VISIBLE_LIMIT && (
            <button
              onClick={toggleShowAllOtherInsights}
              className={`${TOUCH_TARGET_ROW} gap-1 text-xs font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors`}
              aria-expanded={showAllOtherInsights}
            >
              {showAllOtherInsights
                ? "접기"
                : `${otherInsights.length - OTHER_INSIGHTS_VISIBLE_LIMIT}개 더 보기`}
              <ChevronDown
                size={12}
                className={`transition-transform duration-200 ${showAllOtherInsights ? "rotate-180" : ""}`}
              />
            </button>
          )}
        </div>
      )}
    </CollapsibleCard>
  );
}
