import { memo } from "react";
import { ResponsiveContainer, Treemap, Tooltip } from "recharts";
import { useThemeStore } from "@/stores/themeStore";
import { fmtKrwShort } from "@/utils/format";
import { chartTooltipStyle } from "@/utils/chart";
import TreemapCell from "@/components/common/TreemapCell";
import SkeletonCard from "@/components/common/SkeletonCard";

interface TreemapItem {
  name: string;
  ticker?: string | null;
  value: number;
  pct: number;
}

interface Props {
  data: TreemapItem[];
  title?: string;
  height?: number;
  bare?: boolean;
  isLoading?: boolean;
}

function TreemapChart({ data, title, height = 220, bare = false, isLoading }: Props) {
  const isDark = useThemeStore((s) => s.isDark);

  const chart = isLoading ? (
    <SkeletonCard rows={4} height="h-10" />
  ) : data.length === 0 ? (
    <div className="flex items-center justify-center text-gray-300 dark:text-gray-600 text-sm" style={{ height }}>
      데이터 없음
    </div>
  ) : (
    <ResponsiveContainer width="100%" height={height}>
      <Treemap data={data} dataKey="value" content={<TreemapCell />}>
        <Tooltip
          formatter={(value: number, _name: string, props) => [
            `${fmtKrwShort(value)}원 (${(props.payload?.pct ?? 0).toFixed(1)}%)`,
            props.payload?.ticker
              ? `${props.payload.name} (${props.payload.ticker})`
              : props.payload?.name,
          ]}
          {...chartTooltipStyle(isDark)}
        />
      </Treemap>
    </ResponsiveContainer>
  );

  if (bare) {
    return (
      <div>
        {title && (
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-2">{title}</p>
        )}
        {chart}
      </div>
    );
  }

  return (
    <div className="card">
      {title && (
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{title}</h3>
      )}
      {chart}
    </div>
  );
}

export default memo(TreemapChart);
