import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartTooltipStyle } from "@/utils/chart";
import type { HistoryPoint } from "@/api/economicIndicators";

interface Props {
  data: HistoryPoint[];
  name: string;
  unit: string;
  isDark: boolean;
}

function formatXDate(dateStr: string): string {
  const parts = dateStr.split("-");
  const year = parts[0].slice(2);
  const month = parseInt(parts[1] ?? "1", 10);
  return `${year}.${month}`;
}

export default function IndicatorHistoryChart({ data, name, unit, isDark }: Props) {
  if (!data.length) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-gray-400 dark:text-gray-500">
        데이터를 불러오는 중...
      </div>
    );
  }

  const values = data.map((d) => d.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const avg = values.reduce((a, b) => a + b, 0) / values.length;

  const yDomain: [number, number] = [
    Math.floor(minVal * 0.999),
    Math.ceil(maxVal * 1.001),
  ];

  const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(isDark);

  return (
    <div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 4, right: 12, left: 0, bottom: 4 }}>
          <XAxis
            dataKey="date"
            tickFormatter={formatXDate}
            tick={{ fontSize: 11, fill: "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={yDomain}
            tickFormatter={(v: number) => (unit === "%" ? `${v}%` : v.toFixed(1))}
            tick={{ fontSize: 11, fill: "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip
            labelFormatter={(label: string) => {
              const parts = label.split("-");
              return `${parts[0]}년 ${parseInt(parts[1] ?? "1", 10)}월`;
            }}
            formatter={(value: number) => [
              unit === "%" ? `${value.toFixed(2)}%` : value.toFixed(1),
              name,
            ]}
            contentStyle={contentStyle}
            labelStyle={labelStyle}
            itemStyle={itemStyle}
          />
          <ReferenceLine
            y={avg}
            stroke={isDark ? "#4B5563" : "#D1D5DB"}
            strokeDasharray="4 4"
            label={{
              value: `평균 ${unit === "%" ? `${avg.toFixed(2)}%` : avg.toFixed(1)}`,
              position: "insideTopRight",
              fontSize: 10,
              fill: isDark ? "#6B7280" : "#9CA3AF",
            }}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#3B82F6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: "#3B82F6" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
