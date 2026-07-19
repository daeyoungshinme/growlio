import { useMemo } from "react";
import { AlertTriangle, CheckCircle, Info } from "lucide-react";
import type { RebalancingAnalysis } from "@/api/rebalancing";
import { CASH_EQUIVALENT_TICKER, CASH_TICKER } from "@/constants/assets";
import DiagnosisInsightList from "./DiagnosisInsightList";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { useCollapsible } from "@/hooks/useCollapsible";

const DEFAULT_THRESHOLD = 5.0;

type DriftStatus = "critical" | "caution" | "stable";

function getDriftStatus(maxDrift: number, threshold: number): DriftStatus {
  if (maxDrift >= threshold) return "critical";
  if (maxDrift >= threshold / 2) return "caution";
  return "stable";
}

// 카드 전체를 상태색으로 채우는 대신, 대시보드 RebalancingStatusCard와 동일하게
// 중립 `.card` 배경 위에 상태별 테두리/링만 얹어 앱 전역의 "진단 카드 강조" 시각 언어를 통일한다.
const STATUS_CONFIG = {
  critical: {
    cardAccent: "border-red-300 dark:border-red-700/60 ring-1 ring-red-200 dark:ring-red-800/40",
    icon: AlertTriangle,
    iconColor: "text-red-600 dark:text-red-400",
    badge: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    label: "리밸런싱 필요",
  },
  caution: {
    cardAccent: "border-amber-300 dark:border-amber-700/60",
    icon: Info,
    iconColor: "text-amber-600 dark:text-amber-400",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    label: "점검 권고",
  },
  stable: {
    cardAccent: "",
    icon: CheckCircle,
    iconColor: "text-green-600 dark:text-green-400",
    badge: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
    label: "포트폴리오 안정",
  },
} satisfies Record<
  DriftStatus,
  {
    cardAccent: string;
    icon: typeof AlertTriangle;
    iconColor: string;
    badge: string;
    label: string;
  }
>;

interface Props {
  analysis: RebalancingAnalysis;
  alertThreshold?: number;
  onExecute?: () => void;
}

export default function RebalancingDiagnosisCard({ analysis, alertThreshold, onExecute }: Props) {
  const threshold = alertThreshold ?? DEFAULT_THRESHOLD;
  const [isOpen, toggleOpen] = useCollapsible(true);

  const { tradeable, maxDrift, driftedCount } = useMemo(() => {
    const tradeable = analysis.items.filter(
      (i) =>
        i.ticker !== CASH_TICKER &&
        i.ticker !== CASH_EQUIVALENT_TICKER &&
        i.market !== "KR_PROPERTY",
    );
    const maxDrift =
      tradeable.length > 0 ? Math.max(...tradeable.map((i) => Math.abs(i.weight_diff_pct))) : 0;
    const driftedCount = tradeable.filter((i) => Math.abs(i.weight_diff_pct) >= threshold).length;
    return { tradeable, maxDrift, driftedCount };
  }, [analysis.items, threshold]);

  const status = getDriftStatus(maxDrift, threshold);
  const cfg = STATUS_CONFIG[status];

  // 이탈 크기 상위 3개 종목 (CASH·KR_PROPERTY·CASH_EQUIVALENT 제외)
  const topDrifted = [...tradeable]
    .sort((a, b) => Math.abs(b.weight_diff_pct) - Math.abs(a.weight_diff_pct))
    .slice(0, 3);

  const subText =
    status === "stable"
      ? `모든 종목이 ±${threshold}% 이내 비중을 유지하고 있습니다`
      : status === "caution"
        ? `최대 ${maxDrift.toFixed(1)}% 이탈 — 모니터링이 필요합니다`
        : `${driftedCount}개 종목이 ±${threshold}% 이상 목표 비중을 이탈했습니다`;

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
      collapsedHint={subText}
      isOpen={isOpen}
      onToggle={toggleOpen}
      cardClassName={`card ${cfg.cardAccent}`.trim()}
    >
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{subText}</p>
      {/* 상위 이탈 종목 */}
      {status !== "stable" && topDrifted.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {topDrifted.map((item) => {
            const diff = item.weight_diff_pct;
            const isOver = diff > 0;
            return (
              <div
                key={item.ticker}
                className="flex items-center gap-1 bg-gray-100 dark:bg-gray-800/60 rounded-lg px-2.5 py-1"
              >
                <span className="text-xs font-medium text-gray-800 dark:text-gray-200">
                  {item.name}
                </span>
                <span
                  className={`text-xs font-bold ${isOver ? "text-red-600 dark:text-red-400" : "text-blue-600 dark:text-blue-400"}`}
                >
                  {isOver ? "▲" : "▼"}
                  {Math.abs(diff).toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* 안정 상태 - 이탈 없음 메시지 */}
      {status === "stable" && tradeable.length > 0 && (
        <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mt-3">
          <CheckCircle size={12} className="text-green-500" />
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
            ⚡ 지금 실행하기
          </button>
        </div>
      )}
    </CollapsibleCard>
  );
}
