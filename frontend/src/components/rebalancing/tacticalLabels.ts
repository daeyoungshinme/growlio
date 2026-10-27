import type { SeriesData } from "@/api/backtest";
import type {
  PullbackStage,
  RegimeWeightsTable,
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

/** 표·편집기의 국면 행 순서 */
export const REGIME_ORDER: TacticalRegime[] = ["RISK_ON", "NEUTRAL", "RISK_OFF"];

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
/** 포트폴리오에 지수 그룹으로 적용되는 자산 — 백엔드 tactical_allocation_service.ASSET_GROUP_KEYS */
export const INDEX_GROUP_ASSETS: ReadonlySet<TacticalAsset> = new Set(["QQQ", "SPY", "DIA"]);

/**
 * 전술 자산 이름 — 백엔드 tactical_allocation_service.ASSET_LABELS. QQQ·SPY·DIA는 지수 그룹(대표 종목+같은 지수
 * 보유 종목, plans/76) 비중이고, QQQ·SPY 가격은 국면 판정·백테스트에만 쓴다.
 */
export const ASSET_LABEL: Record<TacticalAsset, string> = {
  QQQ: "나스닥100",
  SPY: "S&P500",
  DIA: "다우존스",
  QLD: "나스닥100 2배",
  SSO: "S&P500 2배",
  CASH: "현금",
};

/** 화면 문구용 전술 자산 나열("나스닥100·S&P500·…·현금") */
export const TACTICAL_ASSET_LIST_TEXT = TACTICAL_ASSETS.map((a) => ASSET_LABEL[a]).join("·");

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
    .map((a) => `${ASSET_LABEL[a]} ${weights[a] ?? 0}%`)
    .join(" · ");
}

/** 백엔드 tactical_tilt.TILT_LABELS와 같은 문구 유지 */
export const TILT_LABEL: Record<TacticalTilt, string> = {
  FAVOR_QQQ: "나스닥 우위",
  BALANCED: "균형",
  FAVOR_SPY: "S&P500 우위",
};

export const TILT_ORDER: TacticalTilt[] = ["FAVOR_QQQ", "BALANCED", "FAVOR_SPY"];

/** 백엔드 tactical_tilt.DEFAULT_TILT_SHIFT_PCT — 기본은 끔(plans/70: 20년 MDD 악화·회전율의 1/3) */
export const DEFAULT_TILT_SHIFT_PCT = 0;

/** 백엔드 tactical_dip.DEFAULT_DIP_SHIFT_PCT — 기본은 끔 */
export const DEFAULT_DIP_SHIFT_PCT = 0;

export interface TacticalPreset {
  key: "stable" | "balanced" | "growth" | "leveraged";
  label: string;
  description: string;
  weights: RegimeWeightsTable;
  tiltShiftPct: number;
  dipShiftPct: number;
  useMacro: boolean;
  /** 2006~2026 20년 백테스트(현금 국채 이자·거래비용 0.1%·추세 밴드 2%) — plans/70 */
  backtest: { cagrPct: number; mddPct: number; sharpe: number };
}

function presetTable(
  on: Partial<Record<TacticalAsset, number>>,
  neutral: Partial<Record<TacticalAsset, number>>,
  off: Partial<Record<TacticalAsset, number>>,
): RegimeWeightsTable {
  const full = (w: Partial<Record<TacticalAsset, number>>) =>
    Object.fromEntries(TACTICAL_ASSETS.map((a) => [a, w[a] ?? 0])) as Record<TacticalAsset, number>;
  return { RISK_ON: full(on), NEUTRAL: full(neutral), RISK_OFF: full(off) };
}

const BALANCED_TABLE = presetTable(
  { QQQ: 80, SPY: 20 },
  { QQQ: 50, SPY: 20, CASH: 30 },
  { SPY: 20, CASH: 80 },
);

/**
 * 비중표 프리셋 — 신호의 질(샤프 0.74~0.85)은 거의 같고 수익↔낙폭 위치만 다르다(plans/70 스윕).
 * 수치는 나스닥 강세기(2006~2026) 기준이라 사후 편향이 섞여 있다.
 */
export const TACTICAL_PRESETS: TacticalPreset[] = [
  {
    key: "stable",
    label: "안정형",
    description: "기본 비중표 · 매크로 반영",
    weights: presetTable(
      { QQQ: 50, SPY: 40, CASH: 10 },
      { QQQ: 30, SPY: 40, CASH: 30 },
      { QQQ: 10, SPY: 30, CASH: 60 },
    ),
    tiltShiftPct: 0,
    dipShiftPct: 0,
    useMacro: true,
    backtest: { cagrPct: 10.4, mddPct: 24.9, sharpe: 0.84 },
  },
  {
    key: "balanced",
    label: "균형형",
    description: "QQQ 중심 · 매크로 반영",
    weights: BALANCED_TABLE,
    tiltShiftPct: 0,
    dipShiftPct: 0,
    useMacro: true,
    backtest: { cagrPct: 11.1, mddPct: 24.8, sharpe: 0.84 },
  },
  {
    key: "growth",
    label: "성장형",
    description: "QQQ 중심 · 차트 추세만",
    weights: BALANCED_TABLE,
    tiltShiftPct: 0,
    dipShiftPct: 0,
    useMacro: false,
    backtest: { cagrPct: 12.6, mddPct: 24.9, sharpe: 0.85 },
  },
  {
    key: "leveraged",
    label: "레버리지형",
    description: "공격 국면 QLD 60% · 매크로 반영",
    weights: presetTable(
      { QQQ: 40, QLD: 60 },
      { QQQ: 50, SPY: 30, CASH: 20 },
      { SPY: 30, CASH: 70 },
    ),
    tiltShiftPct: 0,
    dipShiftPct: 0,
    useMacro: true,
    backtest: { cagrPct: 15.2, mddPct: 36.9, sharpe: 0.74 },
  },
];

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
  opts: { dcaLinked?: boolean } = {},
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
  // 적립 보조 모드(자동매수 전술 연동, plans/71) — 비중 적용 대신 방어 국면에만 매수를 보류한다
  if (opts.dcaLinked) {
    const days = regimeDayCount(status.regime_changed_at, now);
    return regime === "RISK_OFF"
      ? {
          tone: "wait",
          text: "방어 국면 — 이번 적립 매수는 보류돼요(현금 보관 후 다음 매수일에 함께 매수)",
        }
      : {
          tone: "idle",
          text: `적립 매수 정상 진행 · ${REGIME_LABEL[regime]} 국면${days ? ` ${days}일째` : ""}`,
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
