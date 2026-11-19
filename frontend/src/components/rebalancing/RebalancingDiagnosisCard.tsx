import { useQuery } from "@tanstack/react-query";
import { TriangleAlert, CircleCheck, Info } from "lucide-react";
import type { RebalancingAnalysis } from "@/api/rebalancing";
import { driftSummaryQuery } from "@/api/queryOptions";
import DiagnosisInsightList from "./DiagnosisInsightList";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { useCollapsible } from "@/hooks/useCollapsible";
import {
  DRIFT_STATUS_LABEL,
  getItemsDriftStatus,
  isDriftingItem,
  type DriftStatus,
} from "@/utils/portfolio";
import { TIMING_BADGE, TIMING_LABEL, timingMetaParts } from "@/utils/rebalancingTiming";

const DEFAULT_THRESHOLD = 5.0;

// 카드 전체를 상태색으로 채우는 대신 RebalancingStatusCard와 동일하게
// 중립 `.card` 배경 위에 상태별 테두리/링만 얹어 앱 전역의 "진단 카드 강조" 시각 언어를 통일한다.
const STATUS_CONFIG = {
  critical: {
    cardAccent: "border-red-300 dark:border-red-700/60 ring-1 ring-red-200 dark:ring-red-800/40",
    icon: TriangleAlert,
    iconColor: "text-red-600 dark:text-red-400",
    badge: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    label: DRIFT_STATUS_LABEL.critical,
  },
  caution: {
    cardAccent: "border-amber-300 dark:border-amber-700/60",
    icon: Info,
    iconColor: "text-amber-600 dark:text-amber-400",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    label: DRIFT_STATUS_LABEL.caution,
  },
  stable: {
    cardAccent: "",
    icon: CircleCheck,
    iconColor: "text-green-600 dark:text-green-400",
    badge: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    label: DRIFT_STATUS_LABEL.stable,
  },
} satisfies Record<
  DriftStatus,
  {
    cardAccent: string;
    icon: typeof TriangleAlert;
    iconColor: string;
    badge: string;
    label: string;
  }
>;

interface Props {
  analysis: RebalancingAnalysis;
  alertThreshold?: number;
  portfolioName?: string;
}

export default function RebalancingDiagnosisCard({
  analysis,
  alertThreshold,
  portfolioName,
}: Props) {
  // 기준·시점 판정은 서버 drift-summary 행(진단 탭과 같은 응답, 새 요청 없이 캐시 공유)을 우선 —
  // 상대 이탈 기준·시장 게이트까지 반영된 값이다(plans/136). 아직 없으면 넘겨받은 알림 임계치
  const { data: driftSummaries } = useQuery(driftSummaryQuery);
  const summary = driftSummaries?.find((s) => s.portfolio_id === String(analysis.portfolio_id));
  const threshold = summary?.threshold_pct ?? alertThreshold ?? DEFAULT_THRESHOLD;
  const relativeThreshold = summary?.relative_threshold_pct ?? null;
  // 기본 접힘 — 상태 배지 + 한 줄 힌트로 충분하고, 항목별 이탈은 바로 아래 비중 표가 이미 보여준다
  // (포트폴리오 탭에서 같은 이탈이 4번 노출되던 문제, docs/plans/67 P1-7). 펼침 상태는 기억한다.
  const [isOpen, toggleOpen] = useCollapsible(false, "growlio:rebalancing:diagnosisCardOpen");

  // 서버 알림·진단 요약과 같은 기준 — 예수금·목표 밖 보유 종목까지 모든 항목, 임계치 "초과"(plans/63 P1-3).
  // 예전엔 예수금 등을 빼고 ">="로 세어 "N개 종목 이탈" 알림과 다른 개수가 보였다.
  const items = analysis.items;
  const maxDrift =
    items.length > 0 ? Math.max(...items.map((i) => Math.abs(i.weight_diff_pct))) : 0;
  const driftedCount = items.filter((i) => isDriftingItem(i, threshold, relativeThreshold)).length;
  const status = getItemsDriftStatus(items, threshold, relativeThreshold);
  const cfg = STATUS_CONFIG[status];

  const subText =
    status === "stable"
      ? `모든 종목이 ±${threshold}%${relativeThreshold ? `(목표 대비 ${relativeThreshold}%)` : ""} 이내 비중을 유지하고 있습니다`
      : status === "caution"
        ? `최대 ${maxDrift.toFixed(1)}% 이탈 — 모니터링이 필요합니다`
        : `${driftedCount}개 항목이 목표 비중에서 ±${threshold}%${relativeThreshold ? `(또는 목표 대비 ${relativeThreshold}%)` : ""}를 넘게 벗어났습니다`;

  return (
    <CollapsibleCard
      icon={cfg.icon}
      iconWrapClassName="bg-transparent"
      iconColorClassName={cfg.iconColor}
      title={
        // 선택 포트폴리오 기준(analysis.diagnosis_context) — 진단 탭의 "전체 자산 진단"과 구분(plans/64 S4)
        <span className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            이 포트폴리오 진단
          </span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.badge}`}>
            {cfg.label}
          </span>
        </span>
      }
      headerRight={
        portfolioName && (
          <span className="text-xs text-gray-400 dark:text-gray-500 truncate max-w-[40%]">
            {portfolioName}
          </span>
        )
      }
      collapsedHint={summary?.timing ? `${TIMING_LABEL[summary.timing]} · ${subText}` : subText}
      isOpen={isOpen}
      onToggle={toggleOpen}
      cardClassName={`card ${cfg.cardAccent}`.trim()}
    >
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{subText}</p>

      {/* 안정 상태 - 이탈 없음 메시지 */}
      {status === "stable" && analysis.items.length > 0 && (
        <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mt-3">
          <CircleCheck size={12} className="text-green-500" />
          최대 이탈 {maxDrift.toFixed(1)}% (기준 ±{threshold}%)
        </div>
      )}

      {/* 시점 판정(plans/136) — 진단 탭 행과 같은 서버 판정·보조 정보 */}
      {summary?.timing && (
        <div className="mt-3 text-xs">
          <div className="flex items-center gap-2">
            <span
              className={`font-semibold rounded-full px-1.5 py-0.5 shrink-0 ${TIMING_BADGE[summary.timing]}`}
            >
              {TIMING_LABEL[summary.timing]}
            </span>
            <span className="text-gray-400 dark:text-gray-500">
              {timingMetaParts(summary).join(" · ")}
            </span>
          </div>
          {summary.timing_reason && summary.timing !== "OK" && (
            <p className="mt-1 text-gray-600 dark:text-gray-400">{summary.timing_reason}</p>
          )}
        </div>
      )}

      <DiagnosisInsightList context={analysis.diagnosis_context} />
    </CollapsibleCard>
  );
}
