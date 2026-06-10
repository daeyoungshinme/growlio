import type { PortfolioRisk } from "@/api/aiAnalysis";

interface Props {
  risk: PortfolioRisk;
}

const CONCENTRATION_BADGE: Record<string, string> = {
  낮음: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  보통: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300",
  높음: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
};

export default function AIRiskDiagnosisCard({ risk }: Props) {
  const barWidth = `${(risk.score / 10) * 100}%`;
  const barColor =
    risk.score <= 3 ? "bg-blue-500" : risk.score <= 6 ? "bg-yellow-400" : "bg-red-500";

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">포트폴리오 리스크 진단</h3>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
          <span>리스크 점수</span>
          <span className="font-semibold text-gray-800 dark:text-gray-100">{risk.score} / 10</span>
        </div>
        <div className="h-2 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: barWidth }} />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500 dark:text-gray-400">집중도 위험</span>
        <span
          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
            CONCENTRATION_BADGE[risk.concentration_risk] ??
            "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
          }`}
        >
          {risk.concentration_risk}
        </span>
      </div>

      {risk.sector_bias.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {risk.sector_bias.map((bias, i) => (
            <span
              key={i}
              className="px-2 py-0.5 rounded-full text-xs bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-300"
            >
              {bias}
            </span>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed">{risk.description}</p>
    </div>
  );
}
