import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { chartTooltipStyle } from "../../utils/chart";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2"];

interface Props {
  data: { name: string; value: number; pct: number }[];
  compact?: boolean;
}

export default function AssetAllocationChart({ data, compact = false }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const height = compact ? 128 : 240;
  const innerRadius = compact ? 28 : 60;
  const outerRadius = compact ? 46 : 90;

  return (
    <div className="flex flex-col">
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
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
          {!compact && <Legend />}
        </PieChart>
      </ResponsiveContainer>
      {compact && (
        <div className="flex flex-col gap-0.5 mt-1">
          {data.map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: COLORS[i % COLORS.length] }}
              />
              <span className="text-[10px] text-gray-600 dark:text-gray-400 truncate leading-tight">
                {item.name} {item.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
