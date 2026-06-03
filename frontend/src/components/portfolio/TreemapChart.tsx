import { ResponsiveContainer, Treemap, Tooltip } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { fmtKrwShort } from "../../utils/format";
import { chartTooltipStyle } from "../../utils/chart";
import TreemapCell from "../common/TreemapCell";
import SkeletonCard from "../common/SkeletonCard";

interface TreemapItem {
  name: string;
  ticker?: string;
  value: number;
  pct: number;
}

interface Props {
  data: TreemapItem[];
  title: string;
  isLoading?: boolean;
}

export default function TreemapChart({ data, title, isLoading }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">{title}</h3>
      {isLoading ? (
        <SkeletonCard rows={4} height="h-10" />
      ) : data.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-gray-300 dark:text-gray-600 text-sm">
          데이터 없음
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
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
      )}
    </div>
  );
}
