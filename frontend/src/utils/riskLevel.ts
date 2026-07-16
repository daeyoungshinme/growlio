import type { PortfolioRiskMetrics } from "@/api/risk";

export type RiskLevel = "low" | "medium" | "high";

export interface MetricConfig {
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

function varLevel(pct: number, confidence: 95 | 99): RiskLevel {
  if (confidence === 95) return pct < 2 ? "low" : pct < 5 ? "medium" : "high";
  return pct < 3 ? "low" : pct < 8 ? "medium" : "high";
}

function volatilityLevel(pct: number): RiskLevel {
  return pct < 10 ? "low" : pct < 20 ? "medium" : "high";
}

function betaLevel(beta: number): RiskLevel {
  return beta < 0.8 ? "low" : beta < 1.2 ? "medium" : "high";
}

function diversificationLevel(score: number): RiskLevel {
  // 분산도는 높을수록 좋음 — 낮은 점수가 HIGH 위험
  return score >= 70 ? "low" : score >= 40 ? "medium" : "high";
}

function concentrationLevel(topPct: number): RiskLevel {
  return topPct < 20 ? "low" : topPct < 40 ? "medium" : "high";
}

export function buildMetrics(m: PortfolioRiskMetrics): MetricConfig[] {
  return [
    {
      label: "VaR (95%)",
      value: `${m.var_95_pct.toFixed(2)}%`,
      level: varLevel(m.var_95_pct, 95),
      description: "하루 5% 확률로 이 수치 이상의 손실이 발생할 수 있어요 (역사적 시뮬레이션 기준)",
    },
    {
      label: "VaR (99%)",
      value: `${m.var_99_pct.toFixed(2)}%`,
      level: varLevel(m.var_99_pct, 99),
      description: "극단적 시장 충격(1% 확률) 상황에서 예상되는 최대 일별 손실",
    },
    {
      label: "연간 변동성",
      value: `${m.annualized_volatility_pct.toFixed(1)}%`,
      level: volatilityLevel(m.annualized_volatility_pct),
      description: "1년간 수익률의 평균 등락 폭 — 낮을수록 안정적이며 예측 가능한 수익",
    },
    {
      label: "S&P500 베타",
      value: m.beta_sp500.toFixed(2),
      level: betaLevel(m.beta_sp500),
      description: `S&P500이 1% 오를 때 포트폴리오가 ${m.beta_sp500.toFixed(2)}% 움직임 — 1보다 크면 시장보다 더 큰 폭으로 등락`,
    },
    {
      label: "분산도 점수",
      value: `${m.diversification_score}/100`,
      level: diversificationLevel(m.diversification_score),
      description:
        "종목 간 상관관계가 낮을수록 점수 높음 — 높을수록 시장 충격이 특정 종목에 집중되지 않음",
    },
    {
      label: "최대 종목 비중",
      value: `${m.top_holding_weight_pct.toFixed(1)}%`,
      level: concentrationLevel(m.top_holding_weight_pct),
      description: "단일 종목의 최대 비중 — 낮을수록 특정 종목 악재에 덜 취약한 포트폴리오",
    },
  ];
}

export function summarizeRiskLevel(
  m: PortfolioRiskMetrics,
): { highCount: number; level: keyof typeof SUMMARY_CONFIG } | null {
  if (!m.data_available) return null;
  const highCount = buildMetrics(m).filter((metric) => metric.level === "high").length;
  const level = highCount >= 3 ? "risk" : highCount >= 1 ? "caution" : "safe";
  return { highCount, level };
}
