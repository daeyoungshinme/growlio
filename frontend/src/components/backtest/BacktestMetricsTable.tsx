import { PortfolioMetrics } from "../../api/backtest";
import { pnlColor } from "../../utils/colors";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#DB2777", "#059669"];

interface Props {
  metrics: PortfolioMetrics[];
}

function fmt(n: number, suffix = "%") {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}${suffix}`;
}

export default function BacktestMetricsTable({ metrics }: Props) {
  if (!metrics.length) return null;

  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-2">성과 지표 비교</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700">
              <th className="py-1.5 px-2 text-left font-medium text-gray-400 dark:text-gray-500 uppercase">포트폴리오</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">총수익률</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase">CAGR</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase">MDD</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">Sharpe</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => (
              <tr key={m.name} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="py-2 px-2 font-medium text-gray-800 dark:text-gray-200 whitespace-nowrap">
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-1.5"
                    style={{ backgroundColor: COLORS[i % COLORS.length] }}
                  />
                  {m.name}
                </td>
                <td className={`py-2 px-2 text-right font-medium whitespace-nowrap ${pnlColor(m.total_return_pct)}`}>
                  {fmt(m.total_return_pct)}
                </td>
                <td className={`py-2 px-2 text-right whitespace-nowrap ${pnlColor(m.cagr_pct)}`}>
                  {fmt(m.cagr_pct)}
                </td>
                <td className="py-2 px-2 text-right text-blue-500 whitespace-nowrap">
                  -{m.mdd_pct.toFixed(2)}%
                </td>
                <td className="py-2 px-2 text-right text-gray-700 dark:text-gray-300 whitespace-nowrap">
                  {m.sharpe_ratio.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
