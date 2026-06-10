import { memo } from "react";
import { ResponsiveContainer, Tooltip as RechartsTooltip, Treemap } from "recharts";
import { useThemeStore } from "@/stores/themeStore";
import { fmtKrw } from "@/utils/format";
import TreemapCell from "@/components/common/TreemapCell";
import { chartTooltipStyle } from "@/utils/chart";

interface ChartItem {
  name: string;
  ticker?: string | null;
  value: number;
  pct: number;
}

interface Props {
  data: ChartItem[];
}

export default memo(function PortfolioTreemapChart({ data }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-2">종목별 비중</p>
      <ResponsiveContainer width="100%" height={180}>
        <Treemap data={data} dataKey="value" content={<TreemapCell />}>
          <RechartsTooltip
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
  );
});
