import { useState } from "react";
import { ChevronDown, TrendingDown, TrendingUp } from "lucide-react";
import type { MarketSignalResponse, MarketRiskLevel, VixLevel, YieldCurveState, FearGreedClassification } from "@/api/marketSignals";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";

interface Props {
  signal: MarketSignalResponse;
}

const BANNER_BG: Record<MarketRiskLevel, string> = {
  GREEN: "bg-green-50 border-green-200 dark:bg-green-950/40 dark:border-green-800/40",
  YELLOW: "bg-yellow-50 border-yellow-200 dark:bg-yellow-950/40 dark:border-yellow-800/40",
  RED: "bg-red-50 border-red-200 dark:bg-red-950/40 dark:border-red-800/40",
};

const SHORT_IMPLICATION: Record<MarketRiskLevel, string> = {
  GREEN: "계획대로 진행",
  YELLOW: "분할 집행 권장",
  RED: "포지션 점검 필요",
};

const VIX_DOT: Record<VixLevel, string> = {
  LOW: "bg-green-500",
  MEDIUM: "bg-yellow-500",
  MEDIUM_HIGH: "bg-orange-500",
  HIGH: "bg-red-500",
};

const VIX_LABEL: Record<VixLevel, string> = {
  LOW: "낮음",
  MEDIUM: "보통",
  MEDIUM_HIGH: "주의",
  HIGH: "위험",
};

const VIX_HINT: Record<VixLevel, string> = {
  LOW: "시장 안정",
  MEDIUM: "모니터링",
  MEDIUM_HIGH: "분할 집행 고려",
  HIGH: "변동성 급등, 분할 매수 권고",
};

const YIELD_DOT: Record<YieldCurveState, string> = {
  POSITIVE: "bg-green-500",
  FLAT: "bg-yellow-500",
  INVERTED: "bg-orange-500",
  DEEPLY_INVERTED: "bg-red-500",
};

const YIELD_CURVE_LABEL: Record<YieldCurveState, string> = {
  POSITIVE: "정상",
  FLAT: "평탄",
  INVERTED: "역전",
  DEEPLY_INVERTED: "심각 역전",
};

const YIELD_HINT: Record<YieldCurveState, string> = {
  POSITIVE: "경기 확장 국면",
  FLAT: "경기 둔화 가능성",
  INVERTED: "경기 침체 선행 신호",
  DEEPLY_INVERTED: "침체 위험 높음, 안전자산 비중 점검",
};

const FEAR_DOT: Record<FearGreedClassification, string> = {
  EXTREME_FEAR: "bg-blue-500",
  FEAR: "bg-sky-400",
  NEUTRAL: "bg-gray-400",
  GREED: "bg-orange-400",
  EXTREME_GREED: "bg-red-500",
};

const FEAR_HINT: Record<FearGreedClassification, string> = {
  EXTREME_FEAR: "역발상 매수 기회 검토",
  FEAR: "저점 매수 관심 가능",
  NEUTRAL: "중립 유지",
  GREED: "과열 주의, 신규 비중 축소 고려",
  EXTREME_GREED: "탐욕 과열, 차익실현 검토",
};

function scoreColor(score: number): string {
  if (score <= 2) return "text-green-600 dark:text-green-400";
  if (score <= 5) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

export default function MarketSignalBanner({ signal }: Props) {
  const { composite_level, composite_score, data_freshness, signals, fear_greed_contrarian_buy, fear_greed_extreme_greed } = signal;
  const [isOpen, setIsOpen] = useState(composite_level !== "GREEN");

  return (
    <div className={`rounded-xl border ${BANNER_BG[composite_level]}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 flex items-center gap-2">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">시장 위험 신호</span>
        <MarketSignalLevelBadge level={composite_level} />
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">
          {SHORT_IMPLICATION[composite_level]}
          {data_freshness === "STALE" && " · 데이터 조회 불가"}
          {data_freshness === "PARTIAL" && " · 일부 데이터 없음"}
        </span>
        <span className={`text-xs font-semibold shrink-0 ${scoreColor(composite_score)}`}>
          위험지수 {composite_score}/10
        </span>
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 shrink-0 transition-colors ml-1"
          aria-expanded={isOpen}
          aria-label="시장 신호 상세 보기"
        >
          {isOpen ? "접기" : "자세히"}
          <ChevronDown size={11} className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`} />
        </button>
      </div>

      {/* 상세 내용 */}
      {isOpen && (
        <div className="px-4 pb-3 space-y-2.5 border-t border-inherit pt-2.5">
          {/* VIX */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">VIX</span>
            {signals.vix ? (
              <>
                <span className={`w-2 h-2 rounded-full shrink-0 ${VIX_DOT[signals.vix.level]}`} />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.vix.value.toFixed(1)} · {VIX_LABEL[signals.vix.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {VIX_HINT[signals.vix.level]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 장단기 금리차 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">장단기 금리차</span>
            {signals.yield_curve ? (
              <>
                <span className={`w-2 h-2 rounded-full shrink-0 ${YIELD_DOT[signals.yield_curve.state]}`} />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.yield_curve.value.toFixed(2)}% · {YIELD_CURVE_LABEL[signals.yield_curve.state]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {YIELD_HINT[signals.yield_curve.state]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* Fear & Greed */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">Fear &amp; Greed</span>
            {signals.fear_greed ? (
              <>
                <span className={`w-2 h-2 rounded-full shrink-0 ${FEAR_DOT[signals.fear_greed.classification]}`} />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.fear_greed.value} · {signals.fear_greed.label}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {FEAR_HINT[signals.fear_greed.classification]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 특수 플래그 */}
          {fear_greed_contrarian_buy && (
            <div className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200 dark:bg-blue-950/40 dark:border-blue-800/40">
              <TrendingUp size={13} className="text-blue-500 shrink-0" />
              <span className="text-xs text-blue-700 dark:text-blue-300 font-medium">
                역발상 매수 기회 — 극도 공포 구간에서 분할 매수를 고려할 수 있습니다
              </span>
            </div>
          )}
          {fear_greed_extreme_greed && (
            <div className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg bg-orange-50 border border-orange-200 dark:bg-orange-950/40 dark:border-orange-800/40">
              <TrendingDown size={13} className="text-orange-500 shrink-0" />
              <span className="text-xs text-orange-700 dark:text-orange-300 font-medium">
                탐욕 과열 구간 — 신규 비중 확대보다 차익실현 점검을 권장합니다
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
