import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartTooltipStyle } from "../../utils/chart";
import { fmtKrwShort } from "../../utils/format";
import { MONTH_LABELS } from "../../utils/dividendUtils";

interface BarEntry {
  name: string;
  month: number;
  isPast: boolean;
  actual: number;
  estimated: number;
}

interface Props {
  barData: BarEntry[];
  currentYear: number;
  selectedMonth: number;
  isDark: boolean;
  onMonthSelect: (month: number) => void;
}

export default function MonthlyDividendChart({ barData, currentYear, selectedMonth, isDark, onMonthSelect }: Props) {
  return (
    <div className="card">
      <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-4">
        월별 배당 현황 ({currentYear})
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart
          data={barData}
          margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
          onClick={(e) => {
            if (e?.activePayload?.[0]) {
              const d = e.activePayload[0].payload as { month: number };
              onMonthSelect(d.month);
            }
          }}
        >
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v: number) =>
              v >= 1e8 ? `${(v / 1e8).toFixed(1)}억` : v >= 1e4 ? `${Math.round(v / 1e4)}만` : `${v}`
            }
            tick={{ fontSize: 11, fill: "#9CA3AF" }}
            axisLine={false}
            tickLine={false}
            width={48}
          />
          <Tooltip
            formatter={(value: number, name: string) => [
              `${fmtKrwShort(value)}원`,
              name === "actual" ? "실수령" : "예상",
            ]}
            cursor={{ fill: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}
            {...chartTooltipStyle(isDark)}
          />
          <Bar dataKey="actual" stackId="a" radius={[0, 0, 0, 0]} cursor="pointer">
            {barData.map((entry) => (
              <Cell
                key={entry.month}
                fill={entry.month === selectedMonth ? "#15803D" : "#16A34A"}
                opacity={entry.month === selectedMonth ? 1 : 0.75}
              />
            ))}
          </Bar>
          <Bar dataKey="estimated" stackId="a" radius={[4, 4, 0, 0]} cursor="pointer">
            {barData.map((entry) => (
              <Cell
                key={entry.month}
                fill={
                  entry.month === selectedMonth
                    ? (entry.isPast ? "#9CA3AF" : "#4ADE80")
                    : (entry.isPast ? "#D1D5DB" : "#86EFAC")
                }
                opacity={entry.month === selectedMonth ? 1 : 0.75}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="text-xs text-gray-300 dark:text-gray-600 mt-2 text-right">
        진한 초록: 실수령 · 연한 초록: 예상(미래) · 회색: 예상(과거 미수령) | 막대 클릭 시 해당 월 상세 표시
      </p>
    </div>
  );
}

// Re-export for convenience
export { MONTH_LABELS };
