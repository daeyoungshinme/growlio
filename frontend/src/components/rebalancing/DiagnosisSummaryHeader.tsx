import { Activity, AlertTriangle, Shuffle } from "lucide-react";
import type { MarketSignalResponse } from "@/api/marketSignals";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import type { PortfolioRiskMetrics } from "@/api/risk";
import { buildCombinedStatusNote } from "@/utils/diagnosisInsights";
import { summarizeRiskLevel, SUMMARY_CONFIG } from "@/utils/riskLevel";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";

interface Props {
  driftSummaries?: PortfolioDriftSummary[];
  marketSignal?: MarketSignalResponse | null;
  riskMetrics?: PortfolioRiskMetrics;
}

/** 진단 탭 최상단에서 드리프트·시장상황·리스크를 하나의 상태 요약으로 묶어 보여준다.
 * 아래 개별 카드(RebalancingStatusCard/MarketSignalBanner/RiskMetricsCard)는 각자의
 * 상세 배지·노트를 그대로 유지하며, 이 헤더는 그 정보를 대체하지 않고 드릴다운 진입점 역할만 한다. */
export default function DiagnosisSummaryHeader({
  driftSummaries,
  marketSignal,
  riskMetrics,
}: Props) {
  const needsCount = driftSummaries?.filter((s) => s.needs_rebalancing).length ?? 0;
  const riskSummary = riskMetrics ? summarizeRiskLevel(riskMetrics) : null;
  const combinedNote = buildCombinedStatusNote(needsCount, marketSignal?.composite_level);

  const allClear =
    needsCount === 0 &&
    (!marketSignal || marketSignal.composite_level === "GREEN") &&
    (!riskSummary || riskSummary.level === "safe");

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-3">
        <div className="p-1.5 bg-blue-50 dark:bg-blue-950 rounded-lg shrink-0">
          <Shuffle size={16} className="text-blue-600 dark:text-blue-400" />
        </div>
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">투자 현황 요약</h2>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1 text-xs font-semibold rounded-full px-2.5 py-1 ${
            needsCount > 0
              ? "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300"
              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
          }`}
        >
          드리프트 {needsCount}개
        </span>
        {marketSignal && <MarketSignalLevelBadge level={marketSignal.composite_level} />}
        {riskSummary && (
          <span
            className={`inline-flex items-center gap-1 text-xs font-semibold rounded-full px-2.5 py-1 border ${SUMMARY_CONFIG[riskSummary.level].cls}`}
          >
            리스크 {SUMMARY_CONFIG[riskSummary.level].label}
          </span>
        )}
      </div>

      {combinedNote ? (
        <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded-lg px-3 py-1.5 mt-3 flex items-start gap-1.5">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />
          {combinedNote}
        </p>
      ) : allClear ? (
        <p className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5 mt-3">
          <Activity size={13} className="shrink-0" />
          지금은 특별한 조치가 필요하지 않습니다.
        </p>
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
          아래 카드에서 자세한 내용을 확인하세요.
        </p>
      )}
    </div>
  );
}
