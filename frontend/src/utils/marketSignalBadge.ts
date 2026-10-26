import type { MarketRiskLevel } from "@/api/marketSignals";

/** 시장 신호 알약 배지 — 홈 "지금 할 일" 리밸런싱 행과 진단 탭 `RebalancingStatusCard` 공용 */
export const MARKET_SIGNAL_LABEL: Record<MarketRiskLevel, string> = {
  GREEN: "안정",
  YELLOW: "주의",
  RED: "위험",
};

export const MARKET_SIGNAL_BADGE_CLASS: Record<MarketRiskLevel, string> = {
  GREEN: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  YELLOW: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  RED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};
