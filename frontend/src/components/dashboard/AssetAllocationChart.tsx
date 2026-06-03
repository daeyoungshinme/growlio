import { memo } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { chartTooltipStyle } from "../../utils/chart";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2"];

const CONFIG = {
  compact: { height: 180, innerRadius: 38, outerRadius: 70 },
  mobile:  { height: 220, innerRadius: 60, outerRadius: 100 },
  full:    { height: 400, innerRadius: 100, outerRadius: 158 },
};

interface Props {
  data: { name: string; value: number; pct: number }[];
  size?: "compact" | "mobile" | "full";
}

const AssetAllocationChart = memo(function AssetAllocationChart({ data, size = "full" }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const { height, innerRadius, outerRadius } = CONFIG[size];

  return (
    <div className="flex flex-col">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart margin={size === "full" ? undefined : { top: 0, right: 0, bottom: 0, left: 0 }}>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            paddingAngle={3}
            dataKey="value"
          >
            {data.map((_, index) => (
              <Cell key={index} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            {...chartTooltipStyle(isDark)}
            formatter={(value: number) =>
              `${(value / 1e4).toFixed(0)}만원 (${data.find((d) => d.value === value)?.pct.toFixed(1)}%)`
            }
          />
          {size === "full" && <Legend />}
        </PieChart>
      </ResponsiveContainer>
      {size === "compact" && (
        <div className="flex flex-col gap-0.5 mt-1">
          {data.map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
              />
              <span className="text-xs text-gray-600 dark:text-gray-400 truncate leading-tight">
                {item.name} {item.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
      {size === "mobile" && (
        <div className="flex flex-row flex-wrap justify-center gap-x-3 gap-y-1 mt-2">
          {data.map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
              />
              <span className="text-xs text-gray-600 dark:text-gray-400">
                {item.name} {item.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

export default AssetAllocationChart;
