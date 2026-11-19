import type { MarketOutlook } from "@/api/marketSignals";
import type { PortfolioRiskMetrics } from "@/api/risk";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { DIAGNOSIS_ANCHORS } from "@/constants/rebalancingConfig";
import { VERDICT_BADGE_CLASS } from "@/utils/marketOutlook";
import { topConcentration } from "@/utils/riskLevel";

/** 진단 탭 요약 칩 — 이탈·시장 종합 판단·쏠림(plans/137 C3). 화면은 `DiagnosisSummaryStrip` */

export interface DiagnosisChipInput {
  driftSummaries?: PortfolioDriftSummary[];
  outlook?: MarketOutlook;
  risk?: PortfolioRiskMetrics;
}

export interface DiagnosisChip {
  key: string;
  label: string;
  cls: string;
  target: string;
}

const NEUTRAL_CHIP = "bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-200";
const ALERT_CHIP = "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300";

export function buildDiagnosisChips({
  driftSummaries,
  outlook,
  risk,
}: DiagnosisChipInput): DiagnosisChip[] {
  const chips: DiagnosisChip[] = [];
  if (driftSummaries && driftSummaries.length > 0) {
    const needs = driftSummaries.filter((s) => s.needs_rebalancing).length;
    chips.push({
      key: "drift",
      label: needs > 0 ? `이탈 ${needs}개` : "이탈 없음",
      cls: needs > 0 ? ALERT_CHIP : NEUTRAL_CHIP,
      target: DIAGNOSIS_ANCHORS.drift,
    });
  }
  if (outlook && outlook.verdict !== "UNKNOWN") {
    chips.push({
      key: "market",
      label: `시장 ${outlook.label}`,
      cls: VERDICT_BADGE_CLASS[outlook.verdict],
      target: DIAGNOSIS_ANCHORS.market,
    });
  }
  const top = risk?.data_available ? topConcentration(risk) : null;
  if (top) {
    chips.push({
      key: "risk",
      label: `쏠림 ${top.name} ${top.pct.toFixed(0)}%`,
      cls: top.pct >= 60 ? ALERT_CHIP : NEUTRAL_CHIP,
      target: DIAGNOSIS_ANCHORS.risk,
    });
  }
  return chips;
}
