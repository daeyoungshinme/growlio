import type { TacticalAsset, TacticalRegime, TacticalTilt, TrendState } from "@/api/tactical";

/** 백엔드 tactical_allocation_service.REGIME_LABELS와 같은 문구 유지 */
export const REGIME_LABEL: Record<TacticalRegime, string> = {
  RISK_ON: "공격",
  NEUTRAL: "중립",
  RISK_OFF: "방어",
};

export const REGIME_BADGE_CLASS: Record<TacticalRegime, string> = {
  RISK_ON:
    "bg-red-100 text-red-700 border-red-300 dark:bg-red-900/30 dark:text-red-300 dark:border-red-700/40",
  NEUTRAL:
    "bg-gray-100 text-gray-700 border-gray-300 dark:bg-gray-700 dark:text-gray-200 dark:border-gray-600",
  RISK_OFF:
    "bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-700/40",
};

export const TREND_LABEL: Record<TrendState, string> = {
  UP: "상승",
  NEUTRAL: "혼조",
  DOWN: "하락",
  UNKNOWN: "확인 불가",
};

export const TACTICAL_ASSETS: TacticalAsset[] = ["QQQ", "SPY", "DIA", "CASH"];

export const ASSET_LABEL: Record<TacticalAsset, string> = {
  QQQ: "QQQ (나스닥100)",
  SPY: "SPY (S&P500)",
  DIA: "DIA (다우존스)",
  CASH: "현금",
};

/** 백엔드 tactical_tilt.TILT_LABELS와 같은 문구 유지 */
export const TILT_LABEL: Record<TacticalTilt, string> = {
  FAVOR_QQQ: "나스닥 우위",
  BALANCED: "균형",
  FAVOR_SPY: "S&P500 우위",
};

export const TILT_ORDER: TacticalTilt[] = ["FAVOR_QQQ", "BALANCED", "FAVOR_SPY"];

/** 백엔드 tactical_tilt.DEFAULT_TILT_SHIFT_PCT */
export const DEFAULT_TILT_SHIFT_PCT = 10;
