import { memo, useMemo } from "react";
import { ResponsiveContainer, Tooltip, Treemap } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { fmtKrw } from "../../utils/format";
import { pnlColor } from "../../utils/colors";
import type { AllocationItem } from "../../types";
import TreemapCell from "../common/TreemapCell";
import { chartTooltipStyle } from "../../utils/chart";

interface Overview {
  total_stock_krw: number;
  total_invested_krw: number;
  unrealized_pnl_krw: number;
  stock_return_pct: number;
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


export default memo(function PortfolioSummaryCard({ overview, isLoading, stockAllocation }: Props) {
  const isDark = useThemeStore((s) => s.isDark);

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

    </div>
  );
});
