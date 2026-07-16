import { useState } from "react";
import { ChevronDown, ShieldAlert } from "lucide-react";
import type { PortfolioRiskMetrics } from "@/api/risk";
import {
  buildMetrics,
  LEVEL_BADGE,
  SUMMARY_CONFIG,
  summarizeRiskLevel,
  type MetricConfig,
} from "@/utils/riskLevel";

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

  const { highCount, level } = summarizeRiskLevel(metrics)!;
  const summary = SUMMARY_CONFIG[level];

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
