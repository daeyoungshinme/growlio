import { useMemo, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ResponsiveContainer, Tooltip, Treemap } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { fmtKrw } from "../../utils/format";
import { pnlColor } from "../../utils/colors";
import type { PortfolioPosition, AllocationItem } from "../../types";
import TreemapCell from "../common/TreemapCell";
import { chartTooltipStyle } from "../../utils/chart";
import { groupPositionsByTicker } from "../../utils/portfolio";

interface Overview {
  total_stock_krw: number;
  total_invested_krw: number;
  unrealized_pnl_krw: number;
  stock_return_pct: number;
  all_positions: PortfolioPosition[];
}

interface Props {
  overview: Overview | undefined;
  isLoading: boolean;
  stockAllocation?: AllocationItem[];
}

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex-1 text-center">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">{label}</p>
      <p className={`text-lg font-bold mt-0.5 ${color ?? "text-gray-900 dark:text-gray-50"}`}>{value}</p>
    </div>
  );
}


export default function PortfolioSummaryCard({ overview, isLoading, stockAllocation }: Props) {
  const [showAll, setShowAll] = useState(false);
  const isDark = useThemeStore((s) => s.isDark);

  const aggregated = useMemo(
    () => groupPositionsByTicker(overview?.all_positions ?? []).sort((a, b) => b.total_value_krw - a.total_value_krw),
    [overview?.all_positions],
  );

  const chartData = useMemo(
    () =>
      stockAllocation && stockAllocation.length > 0
        ? stockAllocation.map((item) => ({ name: item.name, ticker: item.ticker, value: item.value_krw, pct: item.pct }))
        : null,
    [stockAllocation],
  );

  if (isLoading) {
    return <div className="py-6 text-center text-gray-300 dark:text-gray-600 text-sm">로딩 중...</div>;
  }

  if (!overview) {
    return <div className="py-6 text-center text-gray-300 dark:text-gray-600 text-sm">데이터를 불러올 수 없습니다</div>;
  }

  const pnlColorClass = pnlColor(overview.unrealized_pnl_krw);
  const retColorClass = pnlColor(overview.stock_return_pct);

  return (
    <div className="space-y-4">
      {/* 요약 stat */}
      <div className="flex divide-x divide-gray-100 dark:divide-gray-700">
        <StatBox label="주식 총평가액" value={fmtKrw(Math.round(overview.total_invested_krw / 1e6) * 1e6 + Math.round(overview.unrealized_pnl_krw / 1e6) * 1e6)} />
        <StatBox
          label="평가손익"
          value={`${overview.unrealized_pnl_krw >= 0 ? "+" : ""}${fmtKrw(overview.unrealized_pnl_krw)}`}
          color={pnlColorClass}
        />
        <StatBox
          label="주식 수익률"
          value={`${overview.stock_return_pct >= 0 ? "+" : ""}${overview.stock_return_pct.toFixed(2)}%`}
          color={retColorClass}
        />
      </div>

      {/* 종목별 비중 트리차트 */}
      {chartData ? (
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-2">종목별 비중</p>
          <ResponsiveContainer width="100%" height={180}>
            <Treemap data={chartData} dataKey="value" content={<TreemapCell />}>
              <Tooltip
                {...chartTooltipStyle(isDark)}
                formatter={(value: number, _name: string, props) => [
                  `${fmtKrw(value)} (${(props.payload?.pct ?? 0).toFixed(1)}%)`,
                  props.payload?.ticker
                    ? `${props.payload.name} (${props.payload.ticker})`
                    : props.payload?.name,
                ]}
              />
            </Treemap>
          </ResponsiveContainer>
        </div>
      ) : null}

      {/* 전체 보유 종목 토글 */}
      <div>
        <button
          onClick={() => setShowAll((v) => !v)}
          className="flex items-center justify-between w-full text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 font-medium transition-colors"
        >
          <span>
            전체 보유 종목
            {!showAll && aggregated.length > 0 && (
              <span className="ml-1 text-gray-300 dark:text-gray-600">({aggregated.length}개 종목)</span>
            )}
          </span>
          <ChevronDown
            size={14}
            className={`transition-transform duration-200 ${showAll ? "rotate-180" : ""}`}
          />
        </button>

        {showAll && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[360px] text-xs">
              <thead>
                <tr className="border-b border-gray-100 dark:border-gray-700">
                  <th className="py-1.5 px-2 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
                  <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">수량</th>
                  <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase whitespace-nowrap">평가금액</th>
                  <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">수익</th>
                  <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">비중</th>
                </tr>
              </thead>
              <tbody>
                {aggregated.map((p) => {
                  const pnlColorClass = pnlColor(p.total_pnl);
                  return (
                    <tr key={`${p.ticker}-${p.market}`} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                      <td className="py-2 px-2">
                        <span className="font-medium text-gray-800 dark:text-gray-200">{p.name}</span>
                        <span className="ml-1 text-gray-400 dark:text-gray-500">{p.ticker}</span>
                        <span className="ml-1 text-gray-300 dark:text-gray-600">{p.market}</span>
                      </td>
                      <td className="py-2 px-2 text-right text-gray-600 dark:text-gray-400 whitespace-nowrap">
                        {p.total_qty.toLocaleString()}주
                      </td>
                      <td className="py-2 px-2 text-right text-gray-700 dark:text-gray-300 whitespace-nowrap">{fmtKrw(p.total_value_krw)}</td>
                      <td className={`py-2 px-2 text-right font-medium ${pnlColorClass}`}>
                        <div className="flex flex-col items-end gap-0.5">
                          <span className="whitespace-nowrap">{p.total_pnl >= 0 ? "+" : ""}{fmtKrw(p.total_pnl)}</span>
                          <span className="text-xs font-normal whitespace-nowrap">{p.pnl_pct >= 0 ? "+" : ""}{p.pnl_pct.toFixed(1)}%</span>
                        </div>
                      </td>
                      <td className="py-2 px-2 text-right text-gray-500 dark:text-gray-400 whitespace-nowrap">
                        {p.weight_in_stock.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
