import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import { useInsights } from "@/hooks/useInsights";
import type { Insight, InsightType } from "@/api/insights";

const PORTFOLIO_INSIGHT_TYPES: InsightType[] = [
  "CONCENTRATION",
  "REBALANCING_OPPORTUNITY",
  "TAX_LOSS_HARVEST",
];

const TYPE_LABELS: Partial<Record<InsightType, string>> = {
  CONCENTRATION: "집중도",
  REBALANCING_OPPORTUNITY: "리밸런싱",
  TAX_LOSS_HARVEST: "절세",
};

function DiagnosticGauge({ label, value, max, color }: { label: string; value: number; max: number; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
        <span>{label}</span>
        <span className="font-medium">{value.toFixed(1)}%</span>
      </div>
      <div className="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function InsightRow({ insight }: { insight: Insight }) {
  const navigate = useNavigate();

  const handleAction = () => {
    if (!insight.action_url) return;
    navigate(insight.action_url);
  };

  const severityDot: Record<string, string> = {
    ALERT: "bg-red-500",
    WARNING: "bg-amber-400",
    INFO: "bg-blue-400",
  };

  return (
    <div className="flex items-start gap-3 py-3 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${severityDot[insight.severity] ?? "bg-gray-400"}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-400 dark:text-gray-500">
            {TYPE_LABELS[insight.type] ?? insight.type}
          </span>
          <span className="text-xs font-semibold text-gray-800 dark:text-gray-200">{insight.title}</span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-relaxed">{insight.detail}</p>
        {insight.action_label && (
          <button
            onClick={handleAction}
            className="mt-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
          >
            {insight.action_label} →
          </button>
        )}
      </div>
    </div>
  );
}

interface Props {
  portfolioName?: string;
}

export default function PortfolioDiagnosisCard({ portfolioName }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: allInsights, isLoading } = useInsights();

  if (isLoading) {
    return (
      <div className="card space-y-4">
        <div className="h-4 w-40 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-12 bg-gray-100 dark:bg-gray-700 rounded animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const insights = (allInsights ?? []).filter((i) =>
    PORTFOLIO_INSIGHT_TYPES.includes(i.type as InsightType)
  );

  const concentrationInsight = insights.find((i) => i.type === "CONCENTRATION");
  const concentrationPct = concentrationInsight?.metric_value ?? null;

  if (insights.length === 0) {
    return (
      <div className="card">
        <button
          onClick={() => setIsOpen((v) => !v)}
          className="w-full flex items-center justify-between cursor-pointer"
        >
          <div>
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">포트폴리오 진단 결과</h3>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              {portfolioName ? `'${portfolioName}' 기준` : "전체 자산 기준"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 dark:text-gray-500">✅ 이상 없음</span>
            <ChevronDown
              size={16}
              className={`text-gray-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
            />
          </div>
        </button>
        {isOpen && (
          <div className="mt-5 flex flex-col items-center justify-center py-8 text-center">
            <div className="text-3xl mb-3">✅</div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">포트폴리오 이상 없음</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">현재 발견된 문제가 없습니다</p>
          </div>
        )}
      </div>
    );
  }

  const alertCount = insights.filter((i) => i.severity === "ALERT").length;
  const warnCount = insights.filter((i) => i.severity === "WARNING").length;

  return (
    <div className="card">
      <button
        onClick={() => setIsOpen((v) => !v)}
        className="w-full flex items-center justify-between cursor-pointer"
      >
        <div>
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">포트폴리오 진단 결과</h3>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {portfolioName ? `'${portfolioName}' 기준` : "전체 자산 기준"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {alertCount > 0 && (
            <span className="text-xs font-semibold bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 rounded-full px-2 py-0.5">
              위험 {alertCount}
            </span>
          )}
          {warnCount > 0 && (
            <span className="text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300 rounded-full px-2 py-0.5">
              주의 {warnCount}
            </span>
          )}
          <ChevronDown
            size={16}
            className={`text-gray-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {isOpen && (
        <div className="mt-5 space-y-5">
          {concentrationPct !== null && (
            <div className="space-y-2">
              <DiagnosticGauge
                label="자산 집중도"
                value={concentrationPct}
                max={100}
                color={concentrationPct >= 40 ? "#EF4444" : concentrationPct >= 30 ? "#F59E0B" : "#22C55E"}
              />
            </div>
          )}

          <div>
            <p className="text-xs font-medium text-gray-400 dark:text-gray-500 mb-2">발견된 이슈 ({insights.length}개)</p>
            <div>
              {insights.map((insight, idx) => (
                <InsightRow key={`${insight.type}-${idx}`} insight={insight} />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
