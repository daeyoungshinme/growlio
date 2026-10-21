import { useMemo } from "react";
import { TriangleAlert, CircleCheck, Info, Zap } from "lucide-react";
import type { RebalancingAnalysis } from "@/api/rebalancing";
import DiagnosisInsightList from "./DiagnosisInsightList";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { useCollapsible } from "@/hooks/useCollapsible";
import { DRIFT_STATUS_LABEL, getDriftStatus, type DriftStatus } from "@/utils/portfolio";

const DEFAULT_THRESHOLD = 5.0;

// 카드 전체를 상태색으로 채우는 대신, 대시보드 RebalancingStatusCard와 동일하게
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
  onExecute?: () => void;
  portfolioName?: string;
}

export default function RebalancingDiagnosisCard({
  analysis,
  alertThreshold,
  onExecute,
  portfolioName,
}: Props) {
  const threshold = alertThreshold ?? DEFAULT_THRESHOLD;
  const [isOpen, toggleOpen] = useCollapsible(true);

  // 서버 알림·진단 요약과 같은 기준 — 예수금·목표 밖 보유 종목까지 모든 항목, 임계치 "초과"(plans/63 P1-3).
  // 예전엔 예수금 등을 빼고 ">="로 세어 "N개 종목 이탈" 알림과 다른 개수가 보였다.
  const { maxDrift, driftedCount } = useMemo(() => {
    const items = analysis.items;
    const maxDrift =
      items.length > 0 ? Math.max(...items.map((i) => Math.abs(i.weight_diff_pct))) : 0;
    const driftedCount = items.filter((i) => Math.abs(i.weight_diff_pct) > threshold).length;
    return { maxDrift, driftedCount };
  }, [analysis.items, threshold]);

  const status = getDriftStatus(maxDrift, threshold);
  const cfg = STATUS_CONFIG[status];

  const subText =
    status === "stable"
      ? `모든 종목이 ±${threshold}% 이내 비중을 유지하고 있습니다`
      : status === "caution"
        ? `최대 ${maxDrift.toFixed(1)}% 이탈 — 모니터링이 필요합니다`
        : `${driftedCount}개 항목이 목표 비중에서 ±${threshold}%를 넘게 벗어났습니다`;

  return (
    <CollapsibleCard
      icon={cfg.icon}
      iconWrapClassName="bg-transparent"
      iconColorClassName={cfg.iconColor}
      title={
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.badge}`}>
          {cfg.label}
        </span>
      }
      headerRight={
        portfolioName && (
          <span className="text-xs text-gray-400 dark:text-gray-500 truncate max-w-[40%]">
            {portfolioName}
          </span>
        )
      }
      collapsedHint={subText}
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

      <DiagnosisInsightList context={analysis.diagnosis_context} />

      {/* CRITICAL: 실행 CTA 버튼 */}
      {status === "critical" && onExecute && (
        <div className="mt-3 flex justify-end">
          <button
            onClick={onExecute}
            className="flex items-center gap-1.5 bg-red-600 hover:bg-red-500 text-white text-xs font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            <Zap size={14} /> 지금 실행하기
          </button>
        </div>
      )}
    </CollapsibleCard>
  );
}
