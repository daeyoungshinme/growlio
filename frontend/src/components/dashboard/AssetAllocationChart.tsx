import { memo } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useThemeStore } from "@/stores/themeStore";
import { chartTooltipStyle } from "@/utils/chart";
import { PIE_COLORS } from "@/utils/colors";
import { fmtKrwShort } from "@/utils/format";

const CONFIG = {
  "compact-sm": { height: 140, innerRadius: 30, outerRadius: 56 },
  compact: { height: 200, innerRadius: 50, outerRadius: 88 },
  mobile: { height: 280, innerRadius: 80, outerRadius: 130 },
  full: { height: 400, innerRadius: 100, outerRadius: 158 },
};

interface Props {
  data: { name: string; value: number; pct: number }[];
  size?: "compact-sm" | "compact" | "mobile" | "full";
  fillHeight?: boolean;
  showLegend?: boolean;
}

const AssetAllocationChart = memo(function AssetAllocationChart({
  data,
  size = "full",
  fillHeight = false,
  showLegend = true,
}: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const { height, innerRadius, outerRadius } = CONFIG[size];

  return (
    <div className={fillHeight ? "flex flex-col h-full" : "flex flex-col"}>
      <div className={fillHeight ? "flex-1 min-h-[120px]" : "relative"}>
        <ResponsiveContainer width="100%" height={fillHeight ? "100%" : height}>
          <PieChart margin={size === "full" ? undefined : { top: 0, right: 0, bottom: 0, left: 0 }}>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={fillHeight ? "35%" : innerRadius}
              outerRadius={fillHeight ? "65%" : outerRadius}
              paddingAngle={3}
              dataKey="value"
            >
              {data.map((_, index) => (
                <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              {...chartTooltipStyle(isDark)}
              // 값으로 역조회하면 같은 금액의 조각끼리 비중이 뒤바뀐다 — 조각 자신의 payload 사용
              formatter={(value: number, _name, entry) =>
                `${fmtKrwShort(value)}원 (${(entry.payload as { pct: number }).pct.toFixed(1)}%)`
              }
            />
            {size === "full" && <Legend />}
          </PieChart>
        </ResponsiveContainer>
      </div>
      {showLegend && size === "compact-sm" && (
        <div className="flex flex-row flex-wrap gap-x-2 gap-y-0.5 mt-1">
          {data.map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
              />
              <span className="text-xs text-gray-500 dark:text-gray-400 leading-tight">
                {item.name} {item.pct.toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      )}
      {showLegend && (size === "compact" || size === "mobile") && (
        <div className="flex flex-row flex-wrap justify-center gap-x-3 gap-y-1 mt-2">
          {data.map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <span
                className="inline-block w-2.5 h-2.5 rounded-sm shrink-0"
                style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
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
