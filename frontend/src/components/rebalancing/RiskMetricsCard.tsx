import { useState } from "react";
import { ChevronDown, ShieldAlert } from "lucide-react";
import type { PortfolioRiskMetrics } from "@/api/risk";

type RiskLevel = "low" | "medium" | "high";

interface MetricConfig {
  label: string;
  value: string;
  level: RiskLevel;
  description: string;
}

const LEVEL_BADGE: Record<RiskLevel, { label: string; cls: string }> = {
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

const SUMMARY_CONFIG = {
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

function buildMetrics(m: PortfolioRiskMetrics): MetricConfig[] {
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

function RiskMetricRow({
  metric,
  isExpanded,
  onToggle,
}: {
  metric: MetricConfig;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const badge = LEVEL_BADGE[metric.level];
  const valueColor =
    metric.level === "high"
      ? "text-red-600 dark:text-red-400"
      : metric.level === "medium"
        ? "text-yellow-600 dark:text-yellow-400"
        : "text-green-600 dark:text-green-400";

  return (
    <button
      onClick={onToggle}
      className="w-full py-3 border-b border-gray-100 dark:border-gray-700 last:border-0 text-left"
      aria-expanded={isExpanded}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{metric.label}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-sm font-bold ${valueColor}`}>{metric.value}</span>
          <span className={`text-xs font-semibold px-1.5 py-0.5 rounded-full ${badge.cls}`}>
            {badge.label}
          </span>
          <ChevronDown
            size={12}
            className={`text-gray-400 shrink-0 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
          />
        </div>
      </div>
      {isExpanded && (
        <p className="mt-1.5 text-xs text-gray-400 dark:text-gray-500 leading-relaxed">
          {metric.description}
        </p>
      )}
    </button>
  );
}

export default function RiskMetricsCard({ metrics }: { metrics: PortfolioRiskMetrics }) {
  const [isOpen, setIsOpen] = useState(false);

  const metricList = buildMetrics(metrics);

  const [expandedLabel, setExpandedLabel] = useState<string | null>(
    () => metricList.find((m) => m.level === "high")?.label ?? null,
  );

  if (!metrics.data_available) return null;

  const highCount = metricList.filter((m) => m.level === "high").length;
  const summary =
    highCount >= 3
      ? SUMMARY_CONFIG.risk
      : highCount >= 1
        ? SUMMARY_CONFIG.caution
        : SUMMARY_CONFIG.safe;

  const summaryText =
    highCount === 0
      ? "전반적으로 안정적인 위험 수준입니다."
      : highCount === 1
        ? "일부 지표에서 주의가 필요합니다."
        : highCount === 2
          ? "여러 지표에서 위험 신호가 감지됩니다."
          : "다수 지표가 높은 위험을 나타내고 있습니다.";

  const toggle = (label: string) => setExpandedLabel((prev) => (prev === label ? null : label));

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="flex items-center gap-2"
          aria-expanded={isOpen}
        >
          <div className="p-1.5 bg-orange-50 dark:bg-orange-950 rounded-lg">
            <ShieldAlert size={16} className="text-orange-600 dark:text-orange-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            포트폴리오 위험 지표
          </h2>
          <ChevronDown
            size={14}
            className={`text-gray-500 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {metrics.position_count}개 종목 · 전체 계좌 합산
        </span>
      </div>

      {/* 종합 위험 수준 배너 — 접힌 상태에서도 항상 노출 */}
      <div
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium mb-3 ${summary.cls}`}
      >
        <span className="font-bold">{summary.label}</span>
        <span className="opacity-80">— {summaryText}</span>
      </div>

      {isOpen && (
        <>
          {/* 개별 지표 — 탭하면 설명 표시 */}
          <div>
            {metricList.map((m) => (
              <RiskMetricRow
                key={m.label}
                metric={m}
                isExpanded={expandedLabel === m.label}
                onToggle={() => toggle(m.label)}
              />
            ))}
          </div>

          {/* 참고 기준 */}
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-3 leading-relaxed">
            참고 기준 (S&P500): 연간 변동성 약 15~18% · VaR(95%) 약 1.5~2% · 베타 1.0
          </p>

          {metrics.note && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 leading-relaxed">
              {metrics.note}
            </p>
          )}
        </>
      )}
    </div>
  );
}
