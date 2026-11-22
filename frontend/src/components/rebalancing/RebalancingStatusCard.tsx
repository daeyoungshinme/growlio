import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BellOff, ChevronDown, Shuffle } from "lucide-react";

import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { useInsights } from "@/hooks/useInsights";
import { useCollapsible } from "@/hooks/useCollapsible";
import type { Insight, InsightType, InsightSeverity } from "@/api/insights";
import {
  TIMING_BADGE,
  TIMING_DOT,
  TIMING_LABEL,
  overseasDeductionRoomNote,
  summaryTiming,
  timingHeadline,
  timingMetaParts,
} from "@/utils/rebalancingTiming";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import SkeletonCard from "@/components/common/SkeletonCard";
import { TOUCH_TARGET_MIN_MOBILE_ONLY, TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { driftSummaryQuery, portfoliosQuery, taxSummaryQuery } from "@/api/queryOptions";

const OTHER_INSIGHTS_VISIBLE_LIMIT = 3;

function PortfolioDriftRow({
  summary,
  onClick,
}: {
  summary: PortfolioDriftSummary;
  onClick?: (id: string, openAlert?: boolean) => void;
}) {
  // 시점 판정(plans/136) — 이탈 × 확정 시장 등급 × 자동 실행 게이트. 구버전 응답은 이탈 여부로 대신
  const timing = summaryTiming(summary);
  const urgent = timing === "NOW" || timing === "SPLIT";
  // 구버전 API 응답(필드 없음) 호환을 위해 명시적으로 false일 때만 미설정으로 간주
  const alertNotConfigured = summary.has_alert_configured === false;
  const meta = timingMetaParts(summary);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick?.(summary.portfolio_id)}
      onKeyDown={(e) => {
        // 안쪽 "자동화 설정" 버튼의 키 입력은 그 버튼 몫 — 행 이동까지 겹쳐 실행하지 않는다
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault(); // Space 기본 동작(페이지 스크롤) 차단
          onClick?.(summary.portfolio_id);
        }
      }}
      className="w-full flex flex-col py-2.5 px-3 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/40 text-left transition-colors cursor-pointer"
    >
      <div className="flex items-center gap-2 w-full">
        <span className={`w-2 h-2 rounded-full shrink-0 ${TIMING_DOT[timing]}`} />
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300 flex-1 truncate min-w-0">
          {summary.portfolio_name}
        </span>
        <span
          className={`text-xs font-semibold shrink-0 ${urgent ? "text-red-600 dark:text-red-400" : "text-gray-400 dark:text-gray-500"}`}
        >
          최대 {summary.max_drift_pct.toFixed(1)}%
        </span>
        <span
          className={`text-xs font-semibold rounded-full px-1.5 py-0.5 shrink-0 ${TIMING_BADGE[timing]}`}
        >
          {TIMING_LABEL[timing]}
        </span>
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
      {/* 판정 사유는 안정(OK)이면 생략 — 할 일 없는 행까지 문장을 달면 정작 필요한 행이 묻힌다 */}
      {summary.timing_reason && timing !== "OK" && (
        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1 pl-4">
          {summary.timing_reason}
        </p>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 pl-4">{meta.join(" · ")}</p>
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

/** 리밸런싱 › 진단 탭 상단 카드 — 포트폴리오별 이탈·시점 판정 + 전체 자산 진단. 시장 신호 자체는 탭의
 * MarketSignalBanner가 보여 주고, 이탈과 시장을 겹친 판단은 서버 시점 판정(timing)이 행마다 담는다. */
interface Props {
  onPortfolioSelect?: (id: string, openAlert?: boolean) => void;
  /** 포트폴리오가 하나도 없을 때 보여 주는 "포트폴리오 만들기" CTA */
  emptyStateCta: () => void;
}

// 리밸런싱 기회는 이 카드의 포트폴리오 이탈 행(drift-summary)이 따로 보여 주므로 뺀다
const ALL_INSIGHT_TYPES: InsightType[] = ["CONCENTRATION", "TAX_LOSS_HARVEST"];
const SEVERITY_ORDER: Record<InsightSeverity, number> = { ALERT: 0, WARNING: 1, INFO: 2 };

/** 카드 안 한 영역의 조회 실패 — 영역을 통째로 숨기면 "이탈 없음"·"진단 없음"으로 읽힌다 */
function SectionLoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/40 rounded-lg px-3 py-2 my-2">
      <span>{message}</span>
      <button
        onClick={onRetry}
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-none gap-1 font-medium hover:text-red-600 dark:hover:text-red-300 transition-colors`}
      >
        다시 시도
      </button>
    </div>
  );
}

export default function RebalancingStatusCard({ onPortfolioSelect, emptyStateCta }: Props) {
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
  const {
    data: driftSummaries,
    isError: driftError,
    refetch: refetchDrift,
  } = useQuery(driftSummaryQuery);

  const { data: allInsights, isError: insightsError, refetch: refetchInsights } = useInsights();
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

  const headline = useMemo(() => timingHeadline(driftSummaries ?? []), [driftSummaries]);

  // 복합신호(시장 RED·리스크 과다)는 유저 단위라 모든 행에 같은 문장이 붙던 것을 카드 위 한 줄로(plans/136)
  const compositeReason = driftSummaries?.find((s) => s.has_composite_signal)?.composite_reason;

  // 해외 매도 이익이 예상되는 포트폴리오가 있으면 올해 양도세 기본공제 여유를 알려 준다(시점 판단 보조)
  const hasOverseasGain = (driftSummaries ?? []).some(
    (s) => s.needs_rebalancing && (s.estimated_overseas_gain_krw ?? 0) > 0,
  );
  const { data: taxSummary } = useQuery({
    ...taxSummaryQuery(new Date().getFullYear()),
    enabled: hasOverseasGain,
  });
  const deductionNote = hasOverseasGain ? overseasDeductionRoomNote(taxSummary) : null;

  if (portfoliosLoading) {
    return <SkeletonCard />;
  }

  if (portfoliosError) {
    return (
      <div className="card">
        <SectionLoadError
          message="포트폴리오 현황을 불러오지 못했습니다."
          onRetry={() => void refetchPortfolios()}
        />
      </div>
    );
  }

  if (portfolioCount === 0) {
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
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} justify-start! gap-1 text-xs font-semibold text-blue-600 dark:text-blue-400 hover:underline`}
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
        headline ? (
          <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5 shrink-0">
            {headline}
          </span>
        ) : undefined
      }
      isOpen={isOpen}
      onToggle={toggleOpen}
      cardClassName={cardClass}
    >
      {/* 점검 권장 사유(유저 단위 복합신호) — 행마다 반복하지 않고 한 번만 */}
      {compositeReason && (
        <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-1.5 mb-2">
          점검 권장: {compositeReason}
        </p>
      )}

      {driftError && !driftSummaries && (
        <SectionLoadError
          message="이탈 현황을 불러오지 못했습니다."
          onRetry={() => void refetchDrift()}
        />
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
          {deductionNote && (
            <p className="text-xs text-gray-500 dark:text-gray-400 px-3 pt-1">{deductionNote}</p>
          )}
        </div>
      )}

      {insightsError && !allInsights && (
        <SectionLoadError
          message="전체 자산 진단을 불러오지 못했습니다."
          onRetry={() => void refetchInsights()}
        />
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
