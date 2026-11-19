import type { IndexTrend, MarketOutlookVerdict } from "@/api/marketSignals";

/** 시장 종합 판단(매크로 × 3대 지수 추세) 표시 상수 — 판정은 서버 `market_outlook`(표시 전용, plans/137 B) */

export const OUTLOOK_INDEXES = ["QQQ", "SPY", "DIA"] as const;
export type OutlookIndex = (typeof OUTLOOK_INDEXES)[number];

/** 백엔드 market_outlook.INDEX_NAMES와 같은 이름 */
export const INDEX_NAME: Record<OutlookIndex, string> = {
  QQQ: "나스닥100",
  SPY: "S&P500",
  DIA: "다우",
};

export const VERDICT_BADGE_CLASS: Record<MarketOutlookVerdict, string> = {
  FAVORABLE: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  STEADY: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
  CAUTION: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  DEFENSIVE: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  UNKNOWN: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
};

/** 추세 칩 — 상승 빨강·하락 파랑(한국 관례, ChartTrendList와 같은 색) */
export const TREND_CHIP_CLASS: Record<IndexTrend, string> = {
  UP: "border-red-200 text-red-600 dark:border-red-800/50 dark:text-red-400",
  DOWN: "border-blue-200 text-blue-600 dark:border-blue-800/50 dark:text-blue-400",
  NEUTRAL: "border-gray-200 text-gray-600 dark:border-gray-600 dark:text-gray-300",
  UNKNOWN: "border-gray-200 text-gray-400 dark:border-gray-700 dark:text-gray-500",
};
