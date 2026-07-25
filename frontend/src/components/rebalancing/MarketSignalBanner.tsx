import { useState } from "react";
import { Bell, ChevronDown } from "lucide-react";
import { Link } from "react-router-dom";
import type {
  MarketSignalResponse,
  MarketRiskLevel,
  VixLevel,
  YieldCurveState,
  HighYieldSpreadLevel,
  DollarIndexLevel,
  RateCutExpectationLevel,
  ExchangeRateLevel,
  OilPriceLevel,
  UsRateCurveSignal,
  InflationLevel,
  InflationSignal,
  EmploymentLevel,
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

const YIELD_CURVE_RANK: Record<YieldCurveState, number> = {
  POSITIVE: 0,
  FLAT: 1,
  INVERTED: 2,
  DEEPLY_INVERTED: 3,
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

const RATE_CUT_RANK: Record<RateCutExpectationLevel, number> = {
  NEUTRAL: 0,
  MILD_CUT_EXPECTED: 1,
  CUT_EXPECTED: 2,
  DEEP_CUT_EXPECTED: 3,
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

const EXCHANGE_DOT: Record<ExchangeRateLevel, string> = {
  NORMAL: "bg-green-500",
  ELEVATED: "bg-yellow-500",
  HIGH: "bg-orange-500",
  BREAKOUT: "bg-red-500",
};

const EXCHANGE_LABEL: Record<ExchangeRateLevel, string> = {
  NORMAL: "안정",
  ELEVATED: "약세 전환",
  HIGH: "약세 심화",
  BREAKOUT: "급등 돌파",
};

const EXCHANGE_HINT: Record<ExchangeRateLevel, string> = {
  NORMAL: "환율 안정 국면",
  ELEVATED: "원화 약세 전환 모니터링",
  HIGH: "해외자산 환차익 유리, 원화 약세 우려",
  BREAKOUT: "20일선 상향 돌파, 환헤지 비중 점검",
};

const OIL_DOT: Record<OilPriceLevel, string> = {
  NORMAL: "bg-green-500",
  ELEVATED: "bg-yellow-500",
  HIGH: "bg-orange-500",
  BREAKOUT: "bg-red-500",
};

const OIL_LABEL: Record<OilPriceLevel, string> = {
  NORMAL: "안정",
  ELEVATED: "변동 확대",
  HIGH: "급변동",
  BREAKOUT: "급변동 심화",
};

const OIL_HINT: Record<OilPriceLevel, string> = {
  NORMAL: "유가 안정 국면",
  ELEVATED: "유가 변동성 확대 모니터링",
  HIGH: "인플레이션·경기 우려 확대",
  BREAKOUT: "20일선 대비 급등락, 에너지·인플레이션 민감 자산 점검",
};

const INFLATION_LABEL: Record<InflationLevel, string> = {
  NORMAL: "안정",
  ELEVATED: "완만한 상승",
  HIGH: "높음",
  BREAKOUT: "급등",
};

const INFLATION_HINT: Record<InflationLevel, string> = {
  NORMAL: "물가 안정, Fed 목표(2%) 근접",
  ELEVATED: "목표 대비 소폭 상회, 모니터링",
  HIGH: "목표 상회 지속, 긴축 장기화 우려",
  BREAKOUT: "목표 큰폭 상회, 금리인상 재개 리스크",
};

const INFLATION_RANK: Record<InflationLevel, number> = {
  NORMAL: 0,
  ELEVATED: 1,
  HIGH: 2,
  BREAKOUT: 3,
};

const EMPLOYMENT_LABEL: Record<EmploymentLevel, string> = {
  NORMAL: "안정",
  WATCH: "주시",
  SAHM_TRIGGERED: "경보발동",
  HIGH: "위험",
};

const EMPLOYMENT_HINT: Record<EmploymentLevel, string> = {
  NORMAL: "고용시장 안정",
  WATCH: "실업률 저점 대비 소폭 상승",
  SAHM_TRIGGERED: "Sahm Rule 발동 — 경기침체 신호",
  HIGH: "실업률 급등, 경기침체 우려 확대",
};

/** CPI+PCE 병합 신호의 힌트 — 백엔드가 worst-case(max)로 sub_score를 산정하는 것과
 * 동일한 기준으로, 더 심각한 쪽의 힌트 문구를 선택한다(rateCurveHint와 동일 패턴). */
function inflationHint(signal: InflationSignal): string {
  const cpiRank = signal.cpi_level ? INFLATION_RANK[signal.cpi_level] : -1;
  const pceRank = signal.pce_level ? INFLATION_RANK[signal.pce_level] : -1;
  if (cpiRank >= pceRank) {
    return signal.cpi_level ? INFLATION_HINT[signal.cpi_level] : "";
  }
  return signal.pce_level ? INFLATION_HINT[signal.pce_level] : "";
}

/** sub_score(0~3) 기반 공용 심각도 색상 — 미국 금리 커브 병합 신호처럼 단일 level enum이 없는 경우 사용. */
function subScoreDotColor(subScore: number): string {
  if (subScore <= 0) return "bg-green-500";
  if (subScore === 1) return "bg-yellow-500";
  if (subScore === 2) return "bg-orange-500";
  return "bg-red-500";
}

/** 미국 금리 커브(장단기금리차+금리인하기대) 병합 신호의 힌트 — 백엔드가 worst-case(max)로
 * sub_score를 산정하는 것과 동일한 기준으로, 더 심각한 쪽의 힌트 문구를 선택한다. */
function rateCurveHint(signal: UsRateCurveSignal): string {
  const ycRank = signal.yield_curve_state ? YIELD_CURVE_RANK[signal.yield_curve_state] : -1;
  const rateRank = signal.rate_cut_level ? RATE_CUT_RANK[signal.rate_cut_level] : -1;
  if (ycRank >= rateRank) {
    return signal.yield_curve_state ? YIELD_HINT[signal.yield_curve_state] : "";
  }
  return signal.rate_cut_level ? RATE_HINT[signal.rate_cut_level] : "";
}

function scoreColor(level: MarketRiskLevel): string {
  if (level === "GREEN") return "text-green-600 dark:text-green-400";
  if (level === "YELLOW") return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

export default function MarketSignalBanner({ signal }: Props) {
  const { composite_level, composite_score, composite_score_max, data_freshness, signals } = signal;
  const [isOpen, setIsOpen] = useState(composite_level !== "GREEN");

  const { status: compositeStatus } = useCompositeSignalToggle();

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
          위험지수 {composite_score}/{composite_score_max ?? 27}
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

          {/* 미국 금리 커브 (장단기금리차+금리인하기대 병합) */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              미국 금리 커브
            </span>
            {signals.us_rate_curve ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${subScoreDotColor(signals.us_rate_curve.sub_score)}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.us_rate_curve.yield_curve_value != null &&
                    `10Y-2Y ${signals.us_rate_curve.yield_curve_value.toFixed(2)}%`}
                  {signals.us_rate_curve.yield_curve_state &&
                    ` · ${YIELD_CURVE_LABEL[signals.us_rate_curve.yield_curve_state]}`}
                  {signals.us_rate_curve.rate_cut_value != null &&
                    ` · 2Y-FF ${signals.us_rate_curve.rate_cut_value >= 0 ? "+" : ""}${signals.us_rate_curve.rate_cut_value.toFixed(2)}%p`}
                  {signals.us_rate_curve.rate_cut_level &&
                    ` · ${RATE_LABEL[signals.us_rate_curve.rate_cut_level]}`}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {rateCurveHint(signals.us_rate_curve)}
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

          {/* 원/달러 환율 (참고 지표 — 예측치 아님) */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              원/달러 환율
            </span>
            {signals.exchange_rate ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${EXCHANGE_DOT[signals.exchange_rate.level]}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  ₩{signals.exchange_rate.value.toFixed(0)} ·{" "}
                  {signals.exchange_rate.deviation_pct >= 0 ? "+" : ""}
                  {signals.exchange_rate.deviation_pct.toFixed(1)}% ·{" "}
                  {EXCHANGE_LABEL[signals.exchange_rate.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {EXCHANGE_HINT[signals.exchange_rate.level]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 유가 (WTI, 급등/급락 모두 위험 신호) */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              유가(WTI)
            </span>
            {signals.oil_price ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${OIL_DOT[signals.oil_price.level]}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  ${signals.oil_price.value.toFixed(1)} ·{" "}
                  {signals.oil_price.deviation_pct >= 0 ? "+" : ""}
                  {signals.oil_price.deviation_pct.toFixed(1)}% ·{" "}
                  {OIL_LABEL[signals.oil_price.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {OIL_HINT[signals.oil_price.level]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 인플레이션 (CPI+PCE 병합, Fed 목표 2% 대비 이격도) */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
              인플레이션
            </span>
            {signals.inflation ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${subScoreDotColor(signals.inflation.sub_score)}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {signals.inflation.cpi_yoy_pct != null &&
                    `CPI ${signals.inflation.cpi_yoy_pct >= 0 ? "+" : ""}${signals.inflation.cpi_yoy_pct.toFixed(1)}%`}
                  {signals.inflation.cpi_level &&
                    ` · ${INFLATION_LABEL[signals.inflation.cpi_level]}`}
                  {signals.inflation.pce_yoy_pct != null &&
                    ` · PCE ${signals.inflation.pce_yoy_pct >= 0 ? "+" : ""}${signals.inflation.pce_yoy_pct.toFixed(1)}%`}
                  {signals.inflation.pce_level &&
                    ` · ${INFLATION_LABEL[signals.inflation.pce_level]}`}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {inflationHint(signals.inflation)}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>

          {/* 고용 (실업률 Sahm Rule-lite — 12개월 최저치 대비 상승폭) */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">고용</span>
            {signals.employment ? (
              <>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${subScoreDotColor(signals.employment.sub_score)}`}
                />
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  실업률 {signals.employment.value.toFixed(1)}% ·{" "}
                  {EMPLOYMENT_LABEL[signals.employment.level]}
                </span>
                <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                  {EMPLOYMENT_HINT[signals.employment.level]}
                </span>
              </>
            ) : (
              <span className="text-xs text-gray-400">—</span>
            )}
          </div>
        </div>
      )}

      {/* 시장 위험 신호 알림 현황 — isOpen 상태와 무관하게 항상 표시. 읽기 전용(켜기/끄기는 설정 페이지가 단일 소스),
          배너 상태색과 분리된 중립 배경으로 "알림 영역"임을 구분 */}
      {compositeStatus && (
        <div className="flex flex-col gap-1 px-4 py-2.5 border-t border-inherit bg-gray-50/80 dark:bg-gray-900/40 rounded-b-xl">
          <div className="flex items-center gap-2">
            <Bell size={13} className="text-gray-400 shrink-0" />
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300 shrink-0">
              시장 위험 신호 알림
            </span>
            <span
              className={`text-xs font-semibold shrink-0 ml-auto ${compositeStatus.enabled ? "text-blue-600 dark:text-blue-400" : "text-gray-400 dark:text-gray-500"}`}
            >
              {compositeStatus.enabled ? "받는 중" : "꺼짐"}
            </span>
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
            설정에서 켜기/끄기 →
          </Link>
        </div>
      )}
    </div>
  );
}
