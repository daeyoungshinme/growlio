import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { MarketSignalResponse, MarketRiskLevel, VixLevel, YieldCurveState, FearGreedClassification } from "@/api/marketSignals";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";

interface Props {
  signal: MarketSignalResponse;
}

const BANNER_BG: Record<MarketRiskLevel, string> = {
  GREEN: "bg-green-950/40 border-green-800/40",
  YELLOW: "bg-yellow-950/40 border-yellow-800/40",
  RED: "bg-red-950/40 border-red-800/40",
};

const VIX_LABEL: Record<VixLevel, string> = {
  LOW: "낮음",
  MEDIUM: "중간",
  MEDIUM_HIGH: "높음",
  HIGH: "고위험",
};

const VIX_CLS: Record<VixLevel, string> = {
  LOW: "bg-green-900/30 text-green-400",
  MEDIUM: "bg-yellow-900/30 text-yellow-400",
  MEDIUM_HIGH: "bg-orange-900/30 text-orange-400",
  HIGH: "bg-red-900/30 text-red-400",
};

const YC_LABEL: Record<YieldCurveState, string> = {
  POSITIVE: "정상",
  FLAT: "평탄",
  INVERTED: "역전",
  DEEPLY_INVERTED: "심각 역전",
};

const YC_CLS: Record<YieldCurveState, string> = {
  POSITIVE: "bg-green-900/30 text-green-400",
  FLAT: "bg-yellow-900/30 text-yellow-400",
  INVERTED: "bg-orange-900/30 text-orange-400",
  DEEPLY_INVERTED: "bg-red-900/30 text-red-400",
};

const FG_CLS: Record<FearGreedClassification, string> = {
  EXTREME_FEAR: "bg-green-900/30 text-green-400",
  FEAR: "bg-yellow-900/30 text-yellow-400",
  NEUTRAL: "bg-gray-800 text-gray-300",
  GREED: "bg-orange-900/30 text-orange-400",
  EXTREME_GREED: "bg-red-900/30 text-red-400",
};

export default function MarketSignalBanner({ signal }: Props) {
  const [expanded, setExpanded] = useState(true);
  const { composite_level, signals, fear_greed_contrarian_buy, data_freshness } = signal;
  const { vix, yield_curve, fear_greed } = signals;

  return (
    <div className={`rounded-xl border px-4 py-3 mb-4 ${BANNER_BG[composite_level]}`}>
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-300">시장 위험 신호</span>
          <MarketSignalLevelBadge level={composite_level} />
          {data_freshness === "STALE" && (
            <span className="text-xs text-gray-500">(데이터 조회 불가)</span>
          )}
          {data_freshness === "PARTIAL" && (
            <span className="text-xs text-gray-500">(일부 데이터 없음)</span>
          )}
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-gray-500 hover:text-gray-300 transition-colors"
          aria-label={expanded ? "접기" : "펼치기"}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* 상세 신호 */}
      {expanded && (
        <div className="mt-3 flex flex-wrap gap-2">
          {/* VIX */}
          <div className="flex items-center gap-1.5 bg-gray-900/50 rounded-lg px-3 py-1.5">
            <span className="text-xs text-gray-400">VIX</span>
            {vix ? (
              <>
                <span className="text-xs font-semibold text-gray-100">{vix.value.toFixed(1)}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${VIX_CLS[vix.level]}`}>
                  {VIX_LABEL[vix.level]}
                </span>
                {vix.date && <span className="text-xs text-gray-600">{vix.date}</span>}
              </>
            ) : (
              <span className="text-xs text-gray-600">—</span>
            )}
          </div>

          {/* 장단기 금리차 */}
          <div className="flex items-center gap-1.5 bg-gray-900/50 rounded-lg px-3 py-1.5">
            <span className="text-xs text-gray-400">10Y-2Y</span>
            {yield_curve ? (
              <>
                <span className="text-xs font-semibold text-gray-100">
                  {yield_curve.value >= 0 ? "+" : ""}{yield_curve.value.toFixed(2)}%
                </span>
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${YC_CLS[yield_curve.state]}`}>
                  {YC_LABEL[yield_curve.state]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-600">—</span>
            )}
          </div>

          {/* Fear & Greed */}
          <div className="flex items-center gap-1.5 bg-gray-900/50 rounded-lg px-3 py-1.5">
            <span className="text-xs text-gray-400">F&G</span>
            {fear_greed ? (
              <>
                <span className="text-xs font-semibold text-gray-100">{fear_greed.value}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${FG_CLS[fear_greed.classification]}`}>
                  {fear_greed.label}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-600">—</span>
            )}
          </div>
        </div>
      )}

      {/* 역발상 매수 기회 callout */}
      {expanded && fear_greed_contrarian_buy && (
        <div className="mt-2 text-xs text-green-400 bg-green-950/30 rounded-lg px-3 py-1.5">
          극도의 공포 구간 — 역발상 매수 기회일 수 있습니다
        </div>
      )}
    </div>
  );
}
