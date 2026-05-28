import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { chartTooltipStyle } from "../../utils/chart";

interface Props {
  data: { month: string; total_krw: number }[];
}

export default function MonthlyTrendChart({ data }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const chartData = data.map((d) => {
    const [yearStr, monthStr] = d.month.split("-");
    return {
      month: `${yearStr.slice(2)}.${parseInt(monthStr)}`,
      amount: Math.round(d.total_krw / 1e4),
    };
  });

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 5, right: 10, bottom: 0, left: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#374151" : "#F3F4F6"} />
        <XAxis dataKey="month" tick={{ fontSize: 12, fill: isDark ? "#9CA3AF" : "#6B7280" }} />
        <YAxis tick={{ fontSize: 12, fill: isDark ? "#9CA3AF" : "#6B7280" }} unit="만" />
        <Tooltip
          cursor={{ fill: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)" }}
          formatter={(v: number) => [`${v}만원`, "자산 합계"]}
          {...chartTooltipStyle(isDark)}
        />
        <Bar dataKey="amount" fill="#2563EB" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
