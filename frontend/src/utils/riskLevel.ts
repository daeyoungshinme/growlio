import type { PortfolioRiskMetrics } from "@/api/risk";
import { fmtKrw } from "@/utils/format";

/** 진단 탭 "내 포트폴리오 위험" 카드 행 — 원화 손실액·낙폭·시장 대비·쏠림(plans/137 C). 등급은 절대값이
 * 아니라 시장(S&P500) 수준을 기준으로 잡는다 — 예전 변동성 10/20% 절대 기준은 주식형이면 늘 "보통/높음"이었다. */

export type RiskLevel = "low" | "medium" | "high";

export interface MetricConfig {
  key: "var" | "mdd" | "market" | "concentration";
  label: string;
  value: string;
  level: RiskLevel;
  description: string;
}

export const LEVEL_BADGE: Record<RiskLevel, { label: string; cls: string }> = {
  low: {
    label: "낮음",
    cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  },
  medium: {
    label: "보통",
    cls: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-300",
  },
  high: { label: "높음", cls: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" },
};

export const SUMMARY_CONFIG = {
  safe: {
    label: "안정",
    cls: "bg-blue-50 border-blue-200 text-blue-800 dark:bg-blue-950/30 dark:border-blue-800/40 dark:text-blue-300",
  },
  caution: {
    label: "주의 필요",
    cls: "bg-yellow-50 border-yellow-200 text-yellow-800 dark:bg-yellow-950/30 dark:border-yellow-800/40 dark:text-yellow-300",
  },
  risk: {
    label: "위험",
    cls: "bg-red-50 border-red-200 text-red-800 dark:bg-red-950/30 dark:border-red-800/40 dark:text-red-300",
  },
};

/** 하루 VaR 95% — S&P500이 대략 1.5~2% */
function varLevel(pct: number): RiskLevel {
  return pct < 1.5 ? "low" : pct < 2.5 ? "medium" : "high";
}

/** 1년 최대 낙폭 — S&P500 평년 조정이 10% 안팎 */
function drawdownLevel(pct: number): RiskLevel {
  return pct < 10 ? "low" : pct < 20 ? "medium" : "high";
}

/** S&P500(원화) 대비 변동성 배율 */
function marketRatioLevel(ratio: number): RiskLevel {
  return ratio < 0.8 ? "low" : ratio <= 1.2 ? "medium" : "high";
}

/** 한 지수(또는 한 종목)에 몰린 비중 */
function concentrationLevel(pct: number): RiskLevel {
  return pct < 40 ? "low" : pct < 60 ? "medium" : "high";
}

/** 가장 큰 쏠림 — 지수 기준 상위 노출이 있으면 그것, 없으면 단일 종목 */
export function topConcentration(m: PortfolioRiskMetrics): { name: string; pct: number } | null {
  const topIndex = m.top_index_exposures[0];
  if (topIndex && topIndex.pct_of_stock >= m.top_holding_weight_pct) {
    return { name: topIndex.label, pct: topIndex.pct_of_stock };
  }
  if (m.top_holding_name && m.top_holding_weight_pct > 0) {
    return { name: m.top_holding_name, pct: m.top_holding_weight_pct };
  }
  return topIndex ? { name: topIndex.label, pct: topIndex.pct_of_stock } : null;
}

function marketDescription(m: PortfolioRiskMetrics): string {
  const parts = ["S&P500(원화 환산)과 비교한 흔들림이에요. 1.0배면 시장과 같아요."];
  if (m.sp500_10pct_drop_krw != null && m.beta_sp500 != null) {
    parts.push(
      `S&P500이 10% 빠지면 내 주식은 약 ${fmtKrw(m.sp500_10pct_drop_krw)} 영향을 받아요(베타 ${m.beta_sp500.toFixed(2)}, 주간 기준).`,
    );
  }
  return parts.join(" ");
}

function concentrationDescription(m: PortfolioRiskMetrics): string {
  const parts: string[] = [];
  if (m.top_index_exposures.length > 0) {
    parts.push(
      `지수별: ${m.top_index_exposures.map((e) => `${e.label} ${e.pct_of_stock.toFixed(0)}%`).join(" · ")}`,
    );
  }
  if (m.top_holding_name) {
    parts.push(`가장 큰 종목: ${m.top_holding_name} ${m.top_holding_weight_pct.toFixed(0)}%`);
  }
  parts.push("같은 지수를 따르는 ETF는 국내·해외 상장을 합쳐 셉니다(주식 평가액 대비).");
  return parts.join(" / ");
}

export function buildMetrics(m: PortfolioRiskMetrics): MetricConfig[] {
  const rows: MetricConfig[] = [
    {
      key: "var",
      label: "나쁜 날 예상 손실",
      value: `-${fmtKrw(m.var_95_krw)}`,
      level: varLevel(m.var_95_pct),
      description: `20거래일 중 하루는 이보다 더 잃을 수 있어요(하루 VaR 95%, 총자산의 ${m.var_95_pct.toFixed(1)}%).`,
    },
    {
      key: "mdd",
      label: "1년 최대 낙폭",
      value: `-${m.max_drawdown_pct.toFixed(1)}%`,
      level: drawdownLevel(m.max_drawdown_pct),
      description:
        "최근 1년 동안 고점에서 가장 많이 떨어졌던 폭이에요 — 다시 겪을 수 있는 하락의 크기예요.",
    },
  ];
  if (m.vol_ratio_vs_sp500 != null) {
    rows.push({
      key: "market",
      label: "시장 대비 흔들림",
      value: `${m.vol_ratio_vs_sp500.toFixed(2)}배`,
      level: marketRatioLevel(m.vol_ratio_vs_sp500),
      description: marketDescription(m),
    });
  }
  const top = topConcentration(m);
  if (top) {
    rows.push({
      key: "concentration",
      label: "쏠림",
      value: `${top.name} ${top.pct.toFixed(0)}%`,
      level: concentrationLevel(top.pct),
      description: concentrationDescription(m),
    });
  }
  return rows;
}

export function summarizeRiskLevel(
  m: PortfolioRiskMetrics,
): { highCount: number; level: keyof typeof SUMMARY_CONFIG } | null {
  if (!m.data_available) return null;
  const highCount = buildMetrics(m).filter((metric) => metric.level === "high").length;
  const level = highCount >= 2 ? "risk" : highCount >= 1 ? "caution" : "safe";
  return { highCount, level };
}

/** 접힌 카드·요약 칩 한 줄 — 등급 대신 금액과 쏠림을 바로 보여 준다 */
export function riskHeadline(m: PortfolioRiskMetrics): string | null {
  if (!m.data_available) return null;
  const parts = [`나쁜 날 -${fmtKrw(m.var_95_krw)}`];
  const top = topConcentration(m);
  if (top) parts.push(`${top.name} ${top.pct.toFixed(0)}%`);
  return parts.join(" · ");
}
