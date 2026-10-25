import type {
  PullbackStage,
  TacticalAsset,
  TacticalRegime,
  TacticalTilt,
  TrendState,
} from "@/api/tactical";

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

export const TACTICAL_ASSETS: TacticalAsset[] = ["QQQ", "SPY", "DIA", "QLD", "SSO", "CASH"];

/** 0%면 비중 문구·표에서 생략하는 선택 자산 — 백엔드 tactical_allocation_service.OPTIONAL_ASSETS */
export const OPTIONAL_ASSETS: ReadonlySet<TacticalAsset> = new Set(["DIA", "QLD", "SSO"]);
export const LEVERAGED_ASSETS: ReadonlySet<TacticalAsset> = new Set(["QLD", "SSO"]);

export const ASSET_LABEL: Record<TacticalAsset, string> = {
  QQQ: "QQQ (나스닥100)",
  SPY: "SPY (S&P500)",
  DIA: "DIA (다우존스)",
  QLD: "QLD (나스닥100 2배)",
  SSO: "SSO (S&P500 2배)",
  CASH: "현금",
};

/** 화면 문구용 전술 자산 나열("QQQ·SPY·…·현금") */
export const TACTICAL_ASSET_LIST_TEXT = TACTICAL_ASSETS.map((a) =>
  a === "CASH" ? "현금" : a,
).join("·");

/** 백엔드 tactical_dip.PULLBACK_LABELS와 같은 문구 유지 */
export const PULLBACK_LABEL: Record<PullbackStage, string> = {
  NONE: "웅덩이 없음",
  SMA20: "20일선 눌림",
  SMA60: "60일선 웅덩이",
  SMA120: "120일선 웅덩이",
  SMA120_RSI: "120일선+RSI 과매도",
  UNKNOWN: "확인 불가",
};

/** 웅덩이 단계 배지 — 깊을수록 진하게(색상은 손익 관례와 무관한 중립 앰버 계열) */
export const PULLBACK_BADGE_CLASS: Record<PullbackStage, string> = {
  NONE: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300",
  SMA20: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-300",
  SMA60: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200",
  SMA120: "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-200",
  SMA120_RSI: "bg-orange-200 text-orange-900 dark:bg-orange-800/40 dark:text-orange-100",
  UNKNOWN: "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400",
};

/** 비중 문구 — 백엔드 tactical_allocation_service.format_weights와 같은 규칙(선택 자산은 0%면 생략) */
export function formatTacticalWeights(weights: Partial<Record<TacticalAsset, number>>): string {
  return TACTICAL_ASSETS.filter((a) => !OPTIONAL_ASSETS.has(a) || (weights[a] ?? 0) > 0)
    .map((a) => `${a === "CASH" ? "현금" : a} ${weights[a] ?? 0}%`)
    .join(" · ");
}

/** 백엔드 tactical_tilt.TILT_LABELS와 같은 문구 유지 */
export const TILT_LABEL: Record<TacticalTilt, string> = {
  FAVOR_QQQ: "나스닥 우위",
  BALANCED: "균형",
  FAVOR_SPY: "S&P500 우위",
};

export const TILT_ORDER: TacticalTilt[] = ["FAVOR_QQQ", "BALANCED", "FAVOR_SPY"];

/** 백엔드 tactical_tilt.DEFAULT_TILT_SHIFT_PCT */
export const DEFAULT_TILT_SHIFT_PCT = 10;

/** 백엔드 tactical_dip.DEFAULT_DIP_SHIFT_PCT — 기본은 끔 */
export const DEFAULT_DIP_SHIFT_PCT = 0;
