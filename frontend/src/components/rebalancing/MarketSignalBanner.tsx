import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import type {
  MarketSignalResponse,
  MarketRiskLevel,
  VixLevel,
  YieldCurveState,
  FearGreedClassification,
} from "@/api/marketSignals";
import MarketSignalLevelBadge from "./MarketSignalLevelBadge";

interface Props {
  signal: MarketSignalResponse;
  defaultExpanded?: boolean;
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

const VIX_LABEL: Record<VixLevel, string> = {
  LOW: "낮음",
  MEDIUM: "중간",
  MEDIUM_HIGH: "높음",
  HIGH: "고위험",
};

const VIX_CLS: Record<VixLevel, string> = {
  LOW: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  MEDIUM: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  MEDIUM_HIGH: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  HIGH: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const VIX_DESC: Record<VixLevel, string> = {
  LOW: "시장 변동성 낮음",
  MEDIUM: "정상 시장 범위",
  MEDIUM_HIGH: "불확실성 증가 중",
  HIGH: "시장 공포 구간",
};

const YC_LABEL: Record<YieldCurveState, string> = {
  POSITIVE: "정상",
  FLAT: "평탄",
  INVERTED: "역전",
  DEEPLY_INVERTED: "심각 역전",
};

const YC_CLS: Record<YieldCurveState, string> = {
  POSITIVE: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  FLAT: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  INVERTED: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  DEEPLY_INVERTED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const YC_DESC: Record<YieldCurveState, string> = {
  POSITIVE: "경기 확장 신호",
  FLAT: "경기 전환 주시",
  INVERTED: "경기침체 선행지표",
  DEEPLY_INVERTED: "경기침체 고위험",
};

const FG_CLS: Record<FearGreedClassification, string> = {
  EXTREME_FEAR: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  FEAR: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  NEUTRAL: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
  GREED: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  EXTREME_GREED: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

const FG_DESC: Record<FearGreedClassification, string> = {
  EXTREME_FEAR: "역발상 매수 검토",
  FEAR: "저가 매수 탐색 가능",
  NEUTRAL: "방향성 불명확",
  GREED: "과열 주의",
  EXTREME_GREED: "고점 리스크",
};

const IMPLICATION: Record<MarketRiskLevel, string> = {
  GREEN: "현재 시장은 전반적으로 안정적입니다. 계획된 리밸런싱을 정상 진행하세요.",
  YELLOW: "변동성 확대 구간입니다. 리밸런싱 규모를 분할 집행하거나 현금 비중 유지를 고려하세요.",
  RED: "고위험 구간입니다. 신규 비중 확대보다 기존 포지션 점검과 손실 제한에 집중하세요.",
};

export default function MarketSignalBanner({ signal, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const { composite_level, composite_score, signals, fear_greed_contrarian_buy, fear_greed_extreme_greed, data_freshness } = signal;
  const { vix, yield_curve, fear_greed } = signals;

  return (
    <div className={`rounded-xl border px-4 py-3 ${BANNER_BG[composite_level]}`}>
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">시장 위험 신호</span>
          <MarketSignalLevelBadge level={composite_level} />
          {expanded ? (
            <span className="text-xs text-gray-500 dark:text-gray-500">
              점수 {composite_score.toFixed(1)}/10
            </span>
          ) : (
            <span className="text-xs text-gray-500 dark:text-gray-500">
              {SHORT_IMPLICATION[composite_level]}
            </span>
          )}
          {data_freshness === "STALE" && (
            <span className="text-xs text-gray-500 dark:text-gray-500">(데이터 조회 불가)</span>
          )}
          {data_freshness === "PARTIAL" && (
            <span className="text-xs text-gray-500 dark:text-gray-500">(일부 데이터 없음)</span>
          )}
        </div>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors shrink-0 ml-2 min-h-[44px] min-w-[44px] flex items-center justify-center"
          aria-label={expanded ? "접기" : "펼치기"}
        >
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* 상세 신호 — 가로 스크롤 pill 레이아웃 */}
      {expanded && (
        <div className="mt-3 space-y-3">
          {/* 지표 pill 가로 스크롤 행 */}
          <div className="flex gap-2 overflow-x-auto pb-1 -mx-4 px-4 [&::-webkit-scrollbar]:hidden">
            {/* VIX */}
            {vix && (
              <div className="flex-none rounded-xl border border-gray-200/60 dark:border-gray-700/40 px-3 py-2 bg-white/60 dark:bg-gray-900/50">
                <div className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className="text-xs text-gray-500 dark:text-gray-400">VIX</span>
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-100">{vix.value.toFixed(1)}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${VIX_CLS[vix.level]}`}>
                    {VIX_LABEL[vix.level]}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{VIX_DESC[vix.level]}</p>
              </div>
            )}

            {/* 장단기 금리차 */}
            {yield_curve && (
              <div className="flex-none rounded-xl border border-gray-200/60 dark:border-gray-700/40 px-3 py-2 bg-white/60 dark:bg-gray-900/50">
                <div className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className="text-xs text-gray-500 dark:text-gray-400">10Y-2Y</span>
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-100">
                    {yield_curve.value >= 0 ? "+" : ""}{yield_curve.value.toFixed(2)}%
                  </span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${YC_CLS[yield_curve.state]}`}>
                    {YC_LABEL[yield_curve.state]}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{YC_DESC[yield_curve.state]}</p>
              </div>
            )}

            {/* Fear & Greed */}
            {fear_greed && (
              <div className="flex-none rounded-xl border border-gray-200/60 dark:border-gray-700/40 px-3 py-2 bg-white/60 dark:bg-gray-900/50">
                <div className="flex items-center gap-1.5 whitespace-nowrap">
                  <span className="text-xs text-gray-500 dark:text-gray-400">공포·탐욕</span>
                  <span className="text-xs font-semibold text-gray-700 dark:text-gray-100">{fear_greed.value}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${FG_CLS[fear_greed.classification]}`}>
                    {fear_greed.label}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">{FG_DESC[fear_greed.classification]}</p>
              </div>
            )}
          </div>

          {/* 투자 시사점 */}
          <div className="text-xs rounded-lg px-3 py-2 text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700/40">
            💡 {IMPLICATION[composite_level]}
          </div>

          {/* 역발상 매수 callout */}
          {fear_greed_contrarian_buy && (
            <div className="text-xs text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-950/30 rounded-lg px-3 py-1.5 border border-green-200 dark:border-green-800/40">
              극도의 공포 구간 — 역발상 매수 기회일 수 있습니다
            </div>
          )}

          {/* 극도 탐욕 callout */}
          {fear_greed_extreme_greed && (
            <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 rounded-lg px-3 py-1.5 border border-red-200 dark:border-red-800/40">
              극도의 탐욕 구간 — 고점 리스크가 높습니다. 차익실현을 검토하세요
            </div>
          )}
        </div>
      )}
    </div>
  );
}
