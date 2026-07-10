import { memo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { PortfolioItem } from "@/api/portfolios";

const PIE_COLORS = [
  "#2563EB",
  "#16A34A",
  "#D97706",
  "#DC2626",
  "#7C3AED",
  "#0891B2",
  "#DB2777",
  "#059669",
];

interface Props {
  items: PortfolioItem[];
}

function PortfolioWeightChart({ items }: Props) {
  const validItems = items.filter((i) => (Number(i.weight) || 0) > 0 && i.ticker);
  if (!validItems.length) return null;

  const usedWeight = validItems.reduce((s, i) => s + (Number(i.weight) || 0), 0);
  const remaining = Math.max(0, 100 - usedWeight);
  const maxWeight = Math.max(...validItems.map((i) => Number(i.weight) || 0));
  const pieData = [
    ...validItems.map((i) => ({ name: i.name || i.ticker, value: Number(i.weight) || 0 })),
    ...(remaining > 0.1 ? [{ name: "미배분", value: remaining }] : []),
  ];

  return (
    <div className="mt-3 flex flex-col items-center gap-2">
      {maxWeight > 50 && (
        <div className="w-full text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/40 rounded-lg px-3 py-1.5 text-center">
          단일 종목 비중 {maxWeight.toFixed(1)}% — 집중 투자 위험이 있습니다
        </div>
      )}
      <div className="w-full max-w-[180px]">
        <ResponsiveContainer width="100%" aspect={1}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius="58%"
              outerRadius="89%"
              paddingAngle={2}
              dataKey="value"
              startAngle={90}
              endAngle={-270}
            >
              {pieData.map((_, i) => {
                const isRemainder = remaining > 0.1 && i === pieData.length - 1;
                return (
                  <Cell
                    key={i}
                    fill={isRemainder ? "#9CA3AF" : PIE_COLORS[i % PIE_COLORS.length]}
                    opacity={isRemainder ? 0.4 : 1}
                  />
                );
              })}
            </Pie>
            <Tooltip
              formatter={(value: unknown, name: string) =>
                typeof value === "number" ? [`${value.toFixed(1)}%`, name] : ["-", name]
              }
              contentStyle={{ fontSize: 11, padding: "4px 8px", borderRadius: 6 }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default memo(PortfolioWeightChart);
