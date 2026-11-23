import type { MarketRiskLevel } from "@/api/marketSignals";

/** 시장 신호 등급 라벨·색 단일 정의 — 홈 "지금 할 일" 알약과 `components/rebalancing/MarketSignalLevelBadge`가 공유 */
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
