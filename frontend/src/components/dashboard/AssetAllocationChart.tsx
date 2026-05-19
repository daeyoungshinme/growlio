import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { useThemeStore } from "../../stores/themeStore";

const COLORS = ["#2563EB", "#16A34A", "#D97706", "#DC2626", "#7C3AED", "#0891B2"];

interface Props {
  data: { name: string; value: number; pct: number }[];
}

export default function AssetAllocationChart({ data }: Props) {
  const isDark = useThemeStore((s) => s.isDark);

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={60}
          outerRadius={90}
          paddingAngle={3}
          dataKey="value"
        >
          {data.map((_, index) => (
            <Cell key={index} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            fontSize: 12,
            borderRadius: 8,
            border: `1px solid ${isDark ? "#374151" : "#E5E7EB"}`,
            backgroundColor: isDark ? "#1f2937" : "#ffffff",
            color: isDark ? "#f9fafb" : "#111827",
          }}
          labelStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
          itemStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
          formatter={(value: number) =>
            `${(value / 1e4).toFixed(0)}만원 (${data.find((d) => d.value === value)?.pct.toFixed(1)}%)`
          }
        />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  );
}
