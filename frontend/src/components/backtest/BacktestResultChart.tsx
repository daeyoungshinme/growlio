import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SeriesData } from "../../api/backtest";
import { useThemeStore } from "../../stores/themeStore";
import { chartTooltipStyle } from "../../utils/chart";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2", "#DB2777", "#059669"];

interface Props {
  dates: string[];
  series: SeriesData[];
}

export default function BacktestResultChart({ dates, series }: Props) {
  const isDark = useThemeStore((s) => s.isDark);

  if (!dates.length || !series.length) return null;

  // recharts가 요구하는 [{date, series0, series1, ...}] 형태로 변환
  // null 값은 undefined로 변환 — Recharts가 undefined를 선 갭으로 처리
  const chartData = dates.map((d, i) => {
    const row: Record<string, string | number | undefined> = { date: d.slice(0, 7) }; // "YYYY-MM"
    series.forEach((s) => {
      const v = s.values[i];
      row[s.name] = v == null ? undefined : v;
    });
    return row;
  });

  // X축 tick 간격: 날짜가 많으면 월 단위 중 일부만 표시
  const tickInterval = Math.max(1, Math.floor(dates.length / 12));

  return (
    <div>
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-3">수익률 비교 (기준 = 100)</p>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#374151" : "#F3F4F6"} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: isDark ? "#9CA3AF" : "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            interval={tickInterval}
          />
          <YAxis
            tick={{ fontSize: 10, fill: isDark ? "#9CA3AF" : "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v.toFixed(0)}`}
            width={40}
          />
          <Tooltip
            {...chartTooltipStyle(isDark)}
            formatter={(value: number | null, name: string) => {
              if (value == null) return ["-", name];
              return [
                `${value >= 100 ? "+" : ""}${(value - 100).toFixed(2)}% (${value.toFixed(1)})`,
                name,
              ];
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 12, color: isDark ? "#d1d5db" : undefined }}
            iconType="plainline"
          />
          {series.map((s, i) => (
            <Line
              key={s.name}
              type="monotone"
              dataKey={s.name}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
