import type { SeriesData } from "@/api/backtest";
import type {
  PullbackStage,
  TacticalBacktestResult,
  TacticalAsset,
  TacticalRegime,
  TacticalStatus,
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

/** 전환 조건 안내 꼬리말 — 백엔드 step_confirmation(서로 다른 날 2번 관측) */
export const TRANSITION_CONFIRM_NOTE = "조건을 충족해도 다음 거래일에 한 번 더 확인돼야 전환돼요";

/** 확정 국면이 며칠째인지(바뀐 날 = 1일째, 로컬 날짜 기준). 바뀐 시각이 없으면 null */
export function regimeDayCount(changedAt: string | null, now: Date = new Date()): number | null {
  if (!changedAt) return null;
  const since = new Date(changedAt);
  if (Number.isNaN(since.getTime())) return null;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  return Math.max(1, Math.round((startOf(now) - startOf(since)) / 86_400_000) + 1);
}

export type NextActionTone = "action" | "wait" | "idle";

/**
 * 탭 맨 위 "지금 할 일" 한 줄 — 우선순위: 미사용 → 판정 불가 → 전환 확인 중 → 절반 적용 후 나머지 →
 * 미적용 → 할 일 없음.
 */
export function tacticalNextAction(
  status: TacticalStatus,
  alreadyApplied: boolean,
  now: Date = new Date(),
): { tone: NextActionTone; text: string } {
  const regime = status.confirmed_regime;
  if (!status.enabled) {
    return { tone: "idle", text: "켜면 국면이 바뀔 때 알려드려요" };
  }
  if (!regime) {
    return status.pending_regime
      ? {
          tone: "wait",
          text: `${REGIME_LABEL[status.pending_regime]} 전환 확인 중 — 다음 거래일 확정`,
        }
      : { tone: "wait", text: "시세를 받지 못해 국면을 판정하지 못했어요" };
  }
  if (status.pending_regime) {
    return {
      tone: "wait",
      text: `${REGIME_LABEL[status.pending_regime]} 전환 확인 중 — 다음 거래일 재확인 후 적용하세요`,
    };
  }
  if (status.partial_regime === regime) {
    return { tone: "action", text: "절반 적용함 — 나머지를 적용하세요" };
  }
  if (!alreadyApplied) {
    return { tone: "action", text: `${REGIME_LABEL[regime]} 국면 제안 비중을 적용하세요` };
  }
  const days = regimeDayCount(status.regime_changed_at, now);
  return {
    tone: "idle",
    text: `할 일 없음 · ${REGIME_LABEL[regime]} 국면 유지${days ? ` ${days}일째` : ""}`,
  };
}

/** 백테스트 응답 series(행 단위) → BacktestResultChart 입력(열 단위). 이름은 metrics와 같게 맞춘다 */
export function toChartSeries(data: TacticalBacktestResult): {
  dates: string[];
  series: SeriesData[];
} {
  const rows = data.series;
  const cols: [string, (r: TacticalBacktestResult["series"][number]) => number | undefined][] = [
    ["전술 배분", (r) => r.strategy],
    ["평균 비중 고정", (r) => r.static],
    ["SPY 보유", (r) => r.spy],
    ["QQQ 보유", (r) => r.qqq],
  ];
  if (rows.some((r) => r.dia != null)) cols.push(["DIA 보유", (r) => r.dia]);
  return {
    dates: rows.map((r) => r.date),
    series: cols.map(([name, pick]) => ({ name, values: rows.map((r) => pick(r) ?? null) })),
  };
}
