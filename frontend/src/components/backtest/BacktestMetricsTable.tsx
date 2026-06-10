import { PortfolioMetrics } from "@/api/backtest";
import { pnlColor, LOSS_COLOR } from "@/utils/colors";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#DB2777", "#059669"];

interface Props {
  metrics: PortfolioMetrics[];
}

function fmt(n: number, suffix = "%") {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}${suffix}`;
}

function bestIdx(values: number[], higherIsBetter: boolean): number {
  if (values.length <= 1) return 0;
  return values.reduce((best, v, i) =>
    (higherIsBetter ? v > values[best] : v < values[best]) ? i : best, 0);
}

const HIGHLIGHT = "bg-blue-50 dark:bg-blue-950/40 rounded";

export default function BacktestMetricsTable({ metrics }: Props) {
  if (!metrics.length) return null;

  const bTotal   = bestIdx(metrics.map((m) => m.total_return_pct), true);
  const bCagr    = bestIdx(metrics.map((m) => m.cagr_pct), true);
  const bMdd     = bestIdx(metrics.map((m) => m.mdd_pct), false);
  const bSharpe  = bestIdx(metrics.map((m) => m.sharpe_ratio), true);
  const bVol     = bestIdx(metrics.map((m) => m.volatility_pct), false);
  const bSortino = bestIdx(metrics.map((m) => m.sortino_ratio), true);

  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-2">성과 지표 비교</p>

      {/* 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {metrics.map((m, i) => (
          <div key={m.name} className="py-2.5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                <p className="font-medium text-gray-800 dark:text-gray-200 text-sm truncate">{m.name}</p>
              </div>
              <p className={`text-sm font-semibold shrink-0 ${pnlColor(m.total_return_pct)}`}>{fmt(m.total_return_pct)}</p>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 dark:text-gray-500 flex-wrap pl-3.5">
              <span>CAGR <span className={pnlColor(m.cagr_pct)}>{fmt(m.cagr_pct)}</span></span>
              <span>MDD <span className={LOSS_COLOR}>-{m.mdd_pct.toFixed(2)}%</span></span>
              <span title="단위 위험당 초과 수익률 (높을수록 우수)">Sharpe {m.sharpe_ratio.toFixed(3)}</span>
              <span>변동성 {m.volatility_pct.toFixed(2)}%</span>
              <span title="하방 위험 대비 수익률 (높을수록 우수)">Sortino {m.sortino_ratio.toFixed(3)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700">
              <th className="py-1.5 px-2 text-left font-medium text-gray-400 dark:text-gray-500 uppercase">포트폴리오</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">총수익률</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase">CAGR</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase">MDD</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap" title="단위 위험당 초과 수익률 (높을수록 우수)">Sharpe</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">변동성</th>
              <th className="py-1.5 px-2 text-right font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap" title="하방 위험 대비 수익률 (높을수록 우수)">Sortino</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((m, i) => (
              <tr key={m.name} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                <td className="py-2 px-2 font-medium text-gray-800 dark:text-gray-200 whitespace-nowrap">
                  <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                  {m.name}
                </td>
                <td className={`py-2 px-2 text-right font-medium whitespace-nowrap ${pnlColor(m.total_return_pct)} ${i === bTotal ? HIGHLIGHT : ""}`}>
                  {fmt(m.total_return_pct)}
                </td>
                <td className={`py-2 px-2 text-right whitespace-nowrap ${pnlColor(m.cagr_pct)} ${i === bCagr ? HIGHLIGHT : ""}`}>
                  {fmt(m.cagr_pct)}
                </td>
                <td className={`py-2 px-2 text-right ${LOSS_COLOR} whitespace-nowrap ${i === bMdd ? HIGHLIGHT : ""}`}>
                  -{m.mdd_pct.toFixed(2)}%
                </td>
                <td className={`py-2 px-2 text-right text-gray-700 dark:text-gray-300 whitespace-nowrap ${i === bSharpe ? HIGHLIGHT : ""}`}>
                  {m.sharpe_ratio.toFixed(3)}
                </td>
                <td className={`py-2 px-2 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap ${i === bVol ? HIGHLIGHT : ""}`}>
                  {m.volatility_pct.toFixed(2)}%
                </td>
                <td className={`py-2 px-2 text-right text-gray-700 dark:text-gray-300 whitespace-nowrap ${i === bSortino ? HIGHLIGHT : ""}`}>
                  {m.sortino_ratio.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
