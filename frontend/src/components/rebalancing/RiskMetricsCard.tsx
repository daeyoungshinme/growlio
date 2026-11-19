import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ShieldAlert } from "lucide-react";
import type { PortfolioRiskMetrics } from "@/api/risk";
import { useCollapsible } from "@/hooks/useCollapsible";
import {
  buildMetrics,
  LEVEL_BADGE,
  riskHeadline,
  SUMMARY_CONFIG,
  summarizeRiskLevel,
  type MetricConfig,
} from "@/utils/riskLevel";
import { TOUCH_HEIGHT_MIN, TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { portfolioUrl } from "@/utils/tabUrl";
import { DIAGNOSIS_ANCHORS } from "@/constants/rebalancingConfig";

/** 커버리지가 이보다 낮으면 "일부 종목 제외" 안내 */
const COVERAGE_NOTICE_PCT = 90;

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
        <span className="shrink-0 text-sm font-medium text-gray-700 dark:text-gray-300">
          {metric.label}
        </span>
        {/* 쏠림 값은 긴 ETF 이름이 들어가 390px에서 넘친다 — 값만 줄이고 배지·화살표는 유지 */}
        <div className="flex min-w-0 items-center gap-2">
          <span className={`min-w-0 truncate text-sm font-bold ${valueColor}`} title={metric.value}>
            {metric.value}
          </span>
          <span
            className={`shrink-0 text-xs font-semibold px-1.5 py-0.5 rounded-full ${badge.cls}`}
          >
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
  // 진단 탭 보조 카드라 기본 접힘, 사용자가 펼치면 유지(plans/53 Phase C · plans/64 S4)
  const [isOpen, toggleOpen] = useCollapsible(false, "growlio:rebalancing:risk-metrics-open");

  const metricList = buildMetrics(metrics);

  const [expandedKey, setExpandedKey] = useState<MetricConfig["key"] | null>(
    () => metricList.find((m) => m.level === "high")?.key ?? null,
  );

  const risk = summarizeRiskLevel(metrics); // data_available이 아니면 null
  if (!risk) return null;

  const summary = SUMMARY_CONFIG[risk.level];
  const headline = riskHeadline(metrics);

  const toggle = (key: MetricConfig["key"]) =>
    setExpandedKey((prev) => (prev === key ? null : key));

  return (
    <div id={DIAGNOSIS_ANCHORS.risk} className="card scroll-mt-4">
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={toggleOpen}
          className={`flex items-center gap-2 ${TOUCH_HEIGHT_MIN} -my-2`}
          aria-expanded={isOpen}
        >
          <div className="p-1.5 bg-orange-50 dark:bg-orange-950 rounded-lg">
            <ShieldAlert size={16} className="text-orange-600 dark:text-orange-400" />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            내 포트폴리오 위험
          </h2>
          <ChevronDown
            size={14}
            className={`text-gray-500 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          {metrics.position_count}개 종목 · 예수금 포함
        </span>
      </div>

      {/* 종합 위험 수준 배너 — 접힌 상태에서도 항상 노출 */}
      <div
        className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-medium mb-3 ${summary.cls}`}
      >
        <span className="font-bold shrink-0">{summary.label}</span>
        {headline && <span className="opacity-80 min-w-0">— {headline}</span>}
      </div>

      {isOpen && (
        <>
          {/* 개별 지표 — 탭하면 설명 표시 */}
          <div>
            {metricList.map((m) => (
              <RiskMetricRow
                key={m.key}
                metric={m}
                isExpanded={expandedKey === m.key}
                onToggle={() => toggle(m.key)}
              />
            ))}
          </div>

          <Link
            to={portfolioUrl("종목 현황")}
            className={`${TOUCH_TARGET_ROW} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
          >
            지수·종목 비중 자세히 보기 →
          </Link>

          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 leading-relaxed">
            {metrics.note ?? "최근 1년 원화 기준 추정값"} · 예수금{" "}
            {metrics.cash_weight_pct.toFixed(0)}%
            {metrics.coverage_pct < COVERAGE_NOTICE_PCT &&
              ` · 가격 이력이 없는 종목(평가액의 ${(100 - metrics.coverage_pct).toFixed(0)}%)은 계산에서 뺐어요`}
          </p>
        </>
      )}
    </div>
  );
}
