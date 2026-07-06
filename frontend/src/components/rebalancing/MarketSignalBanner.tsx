import { useState } from "react";
import { Bell, ChevronDown, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import type {
  MarketSignalResponse,
  MarketRiskLevel,
  VixLevel,
  YieldCurveState,
  FearGreedClassification,
  HighYieldSpreadLevel,
  DollarIndexLevel,
  RateCutExpectationLevel,
} from "@/api/marketSignals";
import { useCompositeSignalToggle } from "@/hooks/useCompositeSignalToggle";
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

const HIGH_YIELD_DOT: Record<HighYieldSpreadLevel, string> = {
  NORMAL: "bg-green-500",
  ELEVATED: "bg-yellow-500",
  STRESSED: "bg-orange-500",
  CRISIS: "bg-red-500",
};

const HIGH_YIELD_LABEL: Record<HighYieldSpreadLevel, string> = {
  NORMAL: "정상",
  ELEVATED: "주의",
  STRESSED: "경색",
  CRISIS: "위기",
};

const HIGH_YIELD_HINT: Record<HighYieldSpreadLevel, string> = {
  NORMAL: "신용시장 안정",
  ELEVATED: "신용 스프레드 확대 모니터링",
  STRESSED: "신용 경색 우려, 위험자산 점검",
  CRISIS: "신용 위기 수준, 방어적 포지션 고려",
};

const DOLLAR_DOT: Record<DollarIndexLevel, string> = {
  NORMAL: "bg-green-500",
  ELEVATED: "bg-yellow-500",
  HIGH: "bg-orange-500",
  BREAKOUT: "bg-red-500",
};

const DOLLAR_LABEL: Record<DollarIndexLevel, string> = {
  NORMAL: "안정",
  ELEVATED: "강세",
  HIGH: "급등",
  BREAKOUT: "돌파",
};

const DOLLAR_HINT: Record<DollarIndexLevel, string> = {
  NORMAL: "달러 안정 국면",
  ELEVATED: "달러 강세 전환 모니터링",
  HIGH: "신흥국·원자재 자금 이탈 우려",
  BREAKOUT: "20일선 상향 돌파, 위험자산 비중 점검",
};

const RATE_DOT: Record<RateCutExpectationLevel, string> = {
  NEUTRAL: "bg-green-500",
  MILD_CUT_EXPECTED: "bg-yellow-500",
  CUT_EXPECTED: "bg-orange-500",
  DEEP_CUT_EXPECTED: "bg-red-500",
};

const RATE_LABEL: Record<RateCutExpectationLevel, string> = {
  NEUTRAL: "중립",
  MILD_CUT_EXPECTED: "완만한 인하기대",
  CUT_EXPECTED: "인하기대",
  DEEP_CUT_EXPECTED: "급격한 인하기대",
};

const RATE_HINT: Record<RateCutExpectationLevel, string> = {
  NEUTRAL: "정책금리 유지 전망",
  MILD_CUT_EXPECTED: "인하 기대 소폭 반영",
  CUT_EXPECTED: "금리 인하 기대 확대",
  DEEP_CUT_EXPECTED: "경기둔화 우려, 장기채·성장주 비중 점검",
};

function scoreColor(level: MarketRiskLevel): string {
  if (level === "GREEN") return "text-green-600 dark:text-green-400";
  if (level === "YELLOW") return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

export default function MarketSignalBanner({ signal }: Props) {
  const {
    composite_level,
    composite_score,
    composite_score_max,
    data_freshness,
    signals,
    fear_greed_contrarian_buy,
    fear_greed_extreme_greed,
  } = signal;
  const [isOpen, setIsOpen] = useState(composite_level !== "GREEN");

  const { status: compositeStatus, toggle, isPending } = useCompositeSignalToggle();

  return (
    <div className={`rounded-xl border ${BANNER_BG[composite_level]}`}>
      {/* 헤더 */}
      <div className="px-4 py-3 flex items-center gap-2">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
          시장 위험 신호
        </span>
        <MarketSignalLevelBadge level={composite_level} />
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-1 min-w-0 truncate">
          {SHORT_IMPLICATION[composite_level]}
          {data_freshness === "STALE" && " · 데이터 조회 불가"}
          {data_freshness === "PARTIAL" && " · 일부 데이터 없음"}
        </span>
        <span className={`text-xs font-semibold shrink-0 ${scoreColor(composite_level)}`}>
          위험지수 {composite_score}/{composite_score_max ?? 20}
        </span>
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-0.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 shrink-0 transition-colors ml-1"
          aria-expanded={isOpen}
          aria-label="시장 신호 상세 보기"
        >
          {isOpen ? "접기" : "자세히"}
          <ChevronDown
            size={11}
            className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
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
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              장단기 금리차
            </span>
            {signals.yield_curve ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${YIELD_DOT[signals.yield_curve.state]}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.yield_curve.value.toFixed(2)}% ·{" "}
                  {YIELD_CURVE_LABEL[signals.yield_curve.state]}
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
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              Fear &amp; Greed
            </span>
            {signals.fear_greed ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${FEAR_DOT[signals.fear_greed.classification]}`}
                />
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

          {/* 하이일드 스프레드 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              하이일드 스프레드
            </span>
            {signals.high_yield_spread ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${HIGH_YIELD_DOT[signals.high_yield_spread.level]}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.high_yield_spread.value.toFixed(2)}% ·{" "}
                  {HIGH_YIELD_LABEL[signals.high_yield_spread.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {HIGH_YIELD_HINT[signals.high_yield_spread.level]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 달러 인덱스 */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              달러 인덱스
            </span>
            {signals.dollar_index ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${DOLLAR_DOT[signals.dollar_index.level]}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.dollar_index.deviation_pct >= 0 ? "+" : ""}
                  {signals.dollar_index.deviation_pct.toFixed(1)}% ·{" "}
                  {DOLLAR_LABEL[signals.dollar_index.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {DOLLAR_HINT[signals.dollar_index.level]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 금리인하 기대 (2Y-FEDFUNDS 스프레드, FedWatch 대체지표) */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              금리인하 기대
            </span>
            {signals.rate_cut_expectation ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${RATE_DOT[signals.rate_cut_expectation.level]}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.rate_cut_expectation.value.toFixed(2)}%p ·{" "}
                  {RATE_LABEL[signals.rate_cut_expectation.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {RATE_HINT[signals.rate_cut_expectation.level]}
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

      {/* 시장 위험 신호 알림 설정 — isOpen 상태와 무관하게 항상 표시. 배너 상태색과 분리된 중립 배경으로 "설정 영역"임을 구분 */}
      {compositeStatus && (
        <div className="flex flex-col gap-1 px-4 py-2.5 border-t border-inherit bg-gray-50/80 dark:bg-gray-900/40 rounded-b-xl">
          <div className="flex items-center gap-2">
            <Bell size={13} className="text-gray-400 shrink-0" />
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
              시장 위험 신호 알림 설정
            </span>
            <span
              className={`text-xs font-semibold shrink-0 ${compositeStatus.enabled ? "text-blue-600 dark:text-blue-400" : "text-gray-400 dark:text-gray-500"}`}
            >
              {compositeStatus.enabled ? "받는 중" : "꺼짐"}
            </span>
            <label className="relative inline-flex items-center cursor-pointer shrink-0 ml-auto">
              <input
                type="checkbox"
                checked={compositeStatus.enabled}
                disabled={isPending}
                onChange={(e) => toggle(e.target.checked)}
                className="sr-only peer"
                aria-label="시장 위험 신호 알림 설정 켜기/끄기"
              />
              <div className="w-9 h-5 bg-gray-200 dark:bg-gray-700 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full" />
            </label>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 ml-5">
            {compositeStatus.triggered && compositeStatus.reason
              ? compositeStatus.reason
              : compositeStatus.enabled
                ? "이탈이 없어도 시장/리스크가 위험 수준이면 알림을 보내드려요"
                : "알림이 꺼져 있어 신호를 평가하지 않습니다"}
          </p>
          <Link
            to="/settings?atab=시장 신호 알림"
            className="text-xs text-blue-600 dark:text-blue-400 underline self-start ml-5"
          >
            설정 자세히 보기
          </Link>
        </div>
      )}
    </div>
  );
}
