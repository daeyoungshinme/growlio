import { useNavigate } from "react-router-dom";
import { useInsights } from "@/hooks/useInsights";
import type { Insight, InsightSeverity } from "@/api/insights";

const severityConfig: Record<InsightSeverity, { border: string; bg: string; badge: string; label: string }> = {
  ALERT: {
    border: "border-red-300 dark:border-red-700",
    bg: "bg-red-50 dark:bg-red-900/20",
    badge: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    label: "위험",
  },
  WARNING: {
    border: "border-amber-300 dark:border-amber-700",
    bg: "bg-amber-50 dark:bg-amber-900/20",
    badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
    label: "주의",
  },
  INFO: {
    border: "border-blue-200 dark:border-blue-800",
    bg: "bg-blue-50 dark:bg-blue-900/20",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300",
    label: "정보",
  },
};

function InsightCard({ insight }: { insight: Insight }) {
  const navigate = useNavigate();
  const cfg = severityConfig[insight.severity];

  const handleAction = () => {
    if (!insight.action_url) return;
    const [path, search] = insight.action_url.split("?");
    navigate(path, search ? { state: { tab: search.split("=")[1] } } : undefined);
  };

  return (
    <div className={`rounded-xl border p-4 ${cfg.border} ${cfg.bg}`}>
      <div className="flex items-start gap-3">
        <span className={`shrink-0 mt-0.5 inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${cfg.badge}`}>
          {cfg.label}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{insight.title}</p>
          <p className="mt-0.5 text-xs text-gray-600 dark:text-gray-400 leading-relaxed">{insight.detail}</p>
          {insight.action_label && (
            <button
              onClick={handleAction}
              className="mt-2 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
            >
              {insight.action_label} →
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function InsightsPanel() {
  const { data: insights, isLoading } = useInsights();

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mb-4" />
        <div className="space-y-3">
          {[1, 2].map((i) => (
            <div key={i} className="h-16 bg-gray-100 dark:bg-gray-700 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (!insights || insights.length === 0) return null;

  const alertCount = insights.filter((i) => i.severity === "ALERT").length;
  const warnCount = insights.filter((i) => i.severity === "WARNING").length;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">포트폴리오 진단</h2>
        <div className="flex gap-2">
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
        </div>
      </div>
      <div className="space-y-3">
        {insights.map((insight, idx) => (
          <InsightCard key={`${insight.type}-${idx}`} insight={insight} />
        ))}
      </div>
    </div>
  );
}
