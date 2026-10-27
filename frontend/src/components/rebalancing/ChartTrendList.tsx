import type { TacticalMarket, TechnicalSnapshot } from "@/api/tactical";
import { PULLBACK_BADGE_CLASS, PULLBACK_LABEL, TREND_LABEL } from "./tacticalLabels";

/** QQQ·SPY(·DIA) 차트 지표 행 — 진단 탭 "시장 상황" 카드의 차트 추세 영역(예전 전술 탭 판정 근거에서 이동, plans/82) */

function fmtNum(n: number | null | undefined, digits = 2): string {
  return n == null ? "—" : n.toFixed(digits);
}

/** 종가의 이평선 대비 이격(%) — 음수면 이평선 아래(웅덩이) */
function fmtGap(close: number | null | undefined, ma: number | null | undefined): string {
  if (close == null || ma == null || ma <= 0) return "—";
  const pct = (close / ma - 1) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function IndicatorRow({
  ticker,
  snap,
  note,
  showPullback = false,
}: {
  ticker: string;
  snap?: TechnicalSnapshot;
  note?: string;
  /** 웅덩이 배지 — 투입 판정 기준인 QQQ에만 단다(SPY·DIA는 이격 수치만) */
  showPullback?: boolean;
}) {
  const trend = snap?.trend ?? "UNKNOWN";
  const stage = snap?.pullback_stage;
  const trendCls =
    trend === "UP"
      ? "text-red-500"
      : trend === "DOWN"
        ? "text-blue-500"
        : "text-gray-500 dark:text-gray-400";
  return (
    <div className="py-2 border-t border-gray-200/70 dark:border-gray-700 first:border-t-0">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">
          {ticker}
          {note && (
            <span className="ml-1.5 text-xs font-normal text-gray-400 dark:text-gray-500">
              {note}
            </span>
          )}
        </span>
        <span className="flex items-center gap-2">
          {showPullback && stage && stage !== "UNKNOWN" && (
            <span className={`px-2 py-0.5 rounded-full text-xs ${PULLBACK_BADGE_CLASS[stage]}`}>
              {PULLBACK_LABEL[stage]}
            </span>
          )}
          <span className={`text-sm font-medium ${trendCls}`}>추세 {TREND_LABEL[trend]}</span>
        </span>
      </div>
      <dl className="mt-1 grid grid-cols-3 gap-x-3 gap-y-0.5 text-xs text-gray-600 dark:text-gray-300">
        <div>
          <dt className="text-gray-400 dark:text-gray-500">종가</dt>
          <dd>${fmtNum(snap?.close)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">RSI(14)</dt>
          <dd>{fmtNum(snap?.rsi14, 1)}</dd>
        </div>
        <div>
          <dt className="text-gray-400 dark:text-gray-500">52주 고점 대비</dt>
          <dd>{snap?.drawdown_pct == null ? "—" : `${snap.drawdown_pct.toFixed(1)}%`}</dd>
        </div>
        {/* 이평선은 절대 가격 대신 종가 이격으로 — 어느 선까지 눌렸는지(웅덩이 깊이)가 한눈에 보이게 */}
        {(
          [
            ["20일선", snap?.sma20],
            ["60일선", snap?.sma60],
            ["120일선", snap?.sma120],
            ["200일선", snap?.sma200],
          ] as const
        ).map(([label, ma]) => (
          <div key={label}>
            <dt className="text-gray-400 dark:text-gray-500">{label} 대비</dt>
            <dd>{fmtGap(snap?.close, ma)}</dd>
          </div>
        ))}
        <div>
          <dt className="text-gray-400 dark:text-gray-500">MACD 히스토그램</dt>
          <dd>{fmtNum(snap?.macd_hist)}</dd>
        </div>
      </dl>
    </div>
  );
}

export default function ChartTrendList({
  technicals,
}: {
  technicals: TacticalMarket["technicals"];
}) {
  return (
    <div>
      <IndicatorRow ticker="QQQ" snap={technicals.QQQ} showPullback />
      <IndicatorRow ticker="SPY" snap={technicals.SPY} />
      {/* DIA는 조회됐을 때만 — 국면 판단에는 쓰이지 않는 참고 지표 */}
      {technicals.DIA && (
        <IndicatorRow ticker="DIA" snap={technicals.DIA} note="참고 · 국면 판단 미반영" />
      )}
    </div>
  );
}
