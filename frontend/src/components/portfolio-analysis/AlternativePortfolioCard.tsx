import type { AlternativePortfolio } from "@/api/aiAnalysis";
import { weightBarColor } from "@/utils/dividendUtils";

interface Props {
  portfolio: AlternativePortfolio;
}

const RISK_STYLE: Record<string, { border: string; badge: string }> = {
  보수적: {
    border: "border-blue-200 dark:border-blue-800",
    badge: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  },
  중립적: {
    border: "border-gray-200 dark:border-gray-700",
    badge: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
  },
  공격적: {
    border: "border-red-200 dark:border-red-800",
    badge: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  },
};

export default function AlternativePortfolioCard({ portfolio }: Props) {
  const style = RISK_STYLE[portfolio.risk_level] ?? RISK_STYLE["중립적"];

  return (
    <div
      className={`bg-white dark:bg-gray-900 rounded-2xl border ${style.border} p-4 space-y-3`}
    >
      <div className="flex items-center justify-between">
        <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${style.badge}`}>
          {portfolio.risk_level}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400">{portfolio.expected_return}</span>
      </div>

      <div className="space-y-2">
        {portfolio.items.map((item, i) => (
          <div key={`${item.ticker}-${i}`} className="space-y-0.5">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-gray-700 dark:text-gray-300 truncate max-w-[70%]">
                {item.name}
              </span>
              <span className="text-gray-500 dark:text-gray-400">{item.weight}%</span>
            </div>
            <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full ${weightBarColor(item.weight)}`}
                style={{ width: `${Math.min(item.weight, 100)}%` }}
              />
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500 leading-tight">{item.reason}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
