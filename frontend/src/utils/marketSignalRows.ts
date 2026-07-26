import type {
  MarketSignalResponse,
  VixLevel,
  YieldCurveState,
  RateCutExpectationLevel,
  HighYieldSpreadLevel,
  DollarIndexLevel,
  ExchangeRateLevel,
  OilPriceLevel,
  InflationLevel,
  EmploymentLevel,
} from "@/api/marketSignals";

export type SignalTier = "A" | "B" | "C";

export interface SignalRowContent {
  dotColor: string;
  valueText: string;
  hintText: string;
  subScore: number;
}

export interface SignalRowDisplay {
  key: string;
  label: string;
  tier: SignalTier;
  content: SignalRowContent | null;
}

/** sub_score(0 이상) 기반 공용 심각도 색상 — 모든 신호의 버킷 색상 진행(0→초록/1→노랑/2→주황/3+→빨강)이
 * 동일해 레벨 enum별 개별 맵 대신 이 함수 하나로 통일한다. */
export function dotColorForSubScore(subScore: number): string {
  if (subScore <= 0) return "bg-green-500";
  if (subScore === 1) return "bg-yellow-500";
  if (subScore === 2) return "bg-orange-500";
  return "bg-red-500";
}

/** 병합 신호(금리커브+금리인하기대, CPI+PCE)의 "더 심각한 쪽 힌트 선택" 로직 — 백엔드가
 * worst-case(max)로 sub_score를 산정하는 것과 동일한 기준. rank가 없는(null) 쪽은 -1로 취급. */
function pickWorstHint(rankA: number, hintA: string, rankB: number, hintB: string): string {
  return rankA >= rankB ? hintA : hintB;
}

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

/** 신호 8개를 고정 순서로 표시용 데이터로 변환한다. tier는 백엔드 market_signal_service.py의
 * Tier A(핵심 3개: VIX/하이일드/고용)/B+C(매크로 5개) 분류를 그대로 따른다. */
export function buildSignalRows(signals: MarketSignalResponse["signals"]): SignalRowDisplay[] {
  const rows: SignalRowDisplay[] = [];

  rows.push({
    key: "vix",
    label: "VIX",
    tier: "A",
    content: signals.vix
      ? {
          dotColor: dotColorForSubScore(signals.vix.sub_score),
          valueText: `${signals.vix.value.toFixed(1)} · ${VIX_LABEL[signals.vix.level]}`,
          hintText: VIX_HINT[signals.vix.level],
          subScore: signals.vix.sub_score,
        }
      : null,
  });

  rows.push({
    key: "us_rate_curve",
    label: "미국 금리 커브",
    tier: "B",
    content: signals.us_rate_curve
      ? (() => {
          const s = signals.us_rate_curve!;
          const ycRank = s.yield_curve_state ? YIELD_CURVE_RANK[s.yield_curve_state] : -1;
          const rateRank = s.rate_cut_level ? RATE_CUT_RANK[s.rate_cut_level] : -1;
          const ycHint = s.yield_curve_state ? YIELD_HINT[s.yield_curve_state] : "";
          const rateHint = s.rate_cut_level ? RATE_HINT[s.rate_cut_level] : "";
          const parts: string[] = [];
          if (s.yield_curve_value != null) parts.push(`10Y-2Y ${s.yield_curve_value.toFixed(2)}%`);
          if (s.yield_curve_state) parts.push(YIELD_CURVE_LABEL[s.yield_curve_state]);
          if (s.rate_cut_value != null)
            parts.push(`2Y-FF ${s.rate_cut_value >= 0 ? "+" : ""}${s.rate_cut_value.toFixed(2)}%p`);
          if (s.rate_cut_level) parts.push(RATE_LABEL[s.rate_cut_level]);
          return {
            dotColor: dotColorForSubScore(s.sub_score),
            valueText: parts.join(" · "),
            hintText: pickWorstHint(ycRank, ycHint, rateRank, rateHint),
            subScore: s.sub_score,
          };
        })()
      : null,
  });

  rows.push({
    key: "high_yield_spread",
    label: "하이일드 스프레드",
    tier: "A",
    content: signals.high_yield_spread
      ? {
          dotColor: dotColorForSubScore(signals.high_yield_spread.sub_score),
          valueText: `${signals.high_yield_spread.value.toFixed(2)}% · ${HIGH_YIELD_LABEL[signals.high_yield_spread.level]}`,
          hintText: HIGH_YIELD_HINT[signals.high_yield_spread.level],
          subScore: signals.high_yield_spread.sub_score,
        }
      : null,
  });

  rows.push({
    key: "dollar_index",
    label: "달러 인덱스",
    tier: "C",
    content: signals.dollar_index
      ? {
          dotColor: dotColorForSubScore(signals.dollar_index.sub_score),
          valueText: `${signals.dollar_index.deviation_pct >= 0 ? "+" : ""}${signals.dollar_index.deviation_pct.toFixed(1)}% · ${DOLLAR_LABEL[signals.dollar_index.level]}`,
          hintText: DOLLAR_HINT[signals.dollar_index.level],
          subScore: signals.dollar_index.sub_score,
        }
      : null,
  });

  rows.push({
    key: "exchange_rate",
    label: "원/달러 환율",
    tier: "C",
    content: signals.exchange_rate
      ? {
          dotColor: dotColorForSubScore(signals.exchange_rate.sub_score),
          valueText: `₩${signals.exchange_rate.value.toFixed(0)} · ${signals.exchange_rate.deviation_pct >= 0 ? "+" : ""}${signals.exchange_rate.deviation_pct.toFixed(1)}% · ${EXCHANGE_LABEL[signals.exchange_rate.level]}`,
          hintText: EXCHANGE_HINT[signals.exchange_rate.level],
          subScore: signals.exchange_rate.sub_score,
        }
      : null,
  });

  rows.push({
    key: "oil_price",
    label: "유가(WTI)",
    tier: "C",
    content: signals.oil_price
      ? {
          dotColor: dotColorForSubScore(signals.oil_price.sub_score),
          valueText: `$${signals.oil_price.value.toFixed(1)} · ${signals.oil_price.deviation_pct >= 0 ? "+" : ""}${signals.oil_price.deviation_pct.toFixed(1)}% · ${OIL_LABEL[signals.oil_price.level]}`,
          hintText: OIL_HINT[signals.oil_price.level],
          subScore: signals.oil_price.sub_score,
        }
      : null,
  });

  rows.push({
    key: "inflation",
    label: "인플레이션",
    tier: "B",
    content: signals.inflation
      ? (() => {
          const s = signals.inflation!;
          const cpiRank = s.cpi_level ? INFLATION_RANK[s.cpi_level] : -1;
          const pceRank = s.pce_level ? INFLATION_RANK[s.pce_level] : -1;
          const cpiHint = s.cpi_level ? INFLATION_HINT[s.cpi_level] : "";
          const pceHint = s.pce_level ? INFLATION_HINT[s.pce_level] : "";
          const parts: string[] = [];
          if (s.cpi_yoy_pct != null)
            parts.push(`CPI ${s.cpi_yoy_pct >= 0 ? "+" : ""}${s.cpi_yoy_pct.toFixed(1)}%`);
          if (s.cpi_level) parts.push(INFLATION_LABEL[s.cpi_level]);
          if (s.pce_yoy_pct != null)
            parts.push(`PCE ${s.pce_yoy_pct >= 0 ? "+" : ""}${s.pce_yoy_pct.toFixed(1)}%`);
          if (s.pce_level) parts.push(INFLATION_LABEL[s.pce_level]);
          return {
            dotColor: dotColorForSubScore(s.sub_score),
            valueText: parts.join(" · "),
            hintText: pickWorstHint(cpiRank, cpiHint, pceRank, pceHint),
            subScore: s.sub_score,
          };
        })()
      : null,
  });

  rows.push({
    key: "employment",
    label: "고용",
    tier: "A",
    content: signals.employment
      ? {
          dotColor: dotColorForSubScore(signals.employment.sub_score),
          valueText: `실업률 ${signals.employment.value.toFixed(1)}% · ${EMPLOYMENT_LABEL[signals.employment.level]}`,
          hintText: EMPLOYMENT_HINT[signals.employment.level],
          subScore: signals.employment.sub_score,
        }
      : null,
  });

  return rows;
}
