import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DCAProjectionPoint } from "../../api/invest";
import { useThemeStore } from "../../stores/themeStore";
import { fmtKrw, fmtKrwShort } from "../../utils/format";

interface Props {
  data: DCAProjectionPoint[];
}

export default function DCAProjectionChart({ data }: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const today = new Date().toISOString().slice(0, 7);
  const pastPoints = data.filter((d) => d.month <= today);
  const futurePoints = data.filter((d) => d.month > today);
  const recentPast = pastPoints.slice(-24);
  const VISIBLE_FUTURE_MONTHS = 36;
  const visibleFuture = futurePoints.slice(0, VISIBLE_FUTURE_MONTHS);
  const hasActualData = data.some((d) => d.actual_krw !== null);
  // 경계점: 마지막 과거 달을 미래 시작점으로도 포함해 실선↔점선이 끊기지 않게
  const boundaryPoint = recentPast.length > 0 ? recentPast[recentPast.length - 1] : null;
  const chartData = [
    ...recentPast.map((d) => ({ ...d, projected_future_krw: undefined })),
    ...(boundaryPoint
      ? [{ ...boundaryPoint, actual_krw: null, projected_future_krw: boundaryPoint.projected_krw, projected_krw: undefined }]
      : []),
    ...(recentPast.length > 0
      ? visibleFuture.map((d) => ({ ...d, actual_krw: null, projected_future_krw: d.projected_krw, projected_krw: undefined }))
      : visibleFuture.map((d) => ({ ...d, projected_future_krw: d.projected_krw }))),
  ];

  const allChartNums = chartData.flatMap((d) => {
    const row = d as Record<string, unknown>;
    return [row.projected_krw, row.projected_future_krw, row.actual_krw];
  }).filter((v): v is number => typeof v === "number" && isFinite(v));
  const actualNums = chartData
    .map((d) => d.actual_krw)
    .filter((v): v is number => typeof v === "number" && isFinite(v));
  const rawMax = allChartNums.length > 0 ? Math.max(...allChartNums) : 0;
  const actualMax = actualNums.length > 0 ? Math.max(...actualNums) : 0;
  const yMax = actualMax > 0 && rawMax > actualMax * 4
    ? Math.ceil(actualMax * 3)
    : Math.ceil(rawMax * 1.05);
  const yDomain: [number, number] = [0, yMax];

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-4">이론 복리 곡선 vs 실제 자산</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#374151" : "#f0f0f0"} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6b7280" }}
            tickFormatter={(v: string) => v.slice(2)}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6b7280" }}
            tickFormatter={(v: number) => fmtKrwShort(v)}
            width={56}
            domain={yDomain}
          />
          <Tooltip
            formatter={(value: number, name: string) => {
              const label =
                name === "projected_krw" || name === "projected_future_krw"
                  ? "이론값"
                  : "실제값";
              return [fmtKrw(value), label];
            }}
            labelFormatter={(label: string) => `${label}`}
            contentStyle={{
              fontSize: 12,
              backgroundColor: isDark ? "#1f2937" : "#ffffff",
              border: `1px solid ${isDark ? "#374151" : "#e5e7eb"}`,
              color: isDark ? "#f9fafb" : "#111827",
            }}
            labelStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
            itemStyle={{ color: isDark ? "#f9fafb" : "#111827" }}
          />
          <Legend
            formatter={(value: string) => {
              if (value === "projected_krw") return "이론 복리 곡선 (과거)";
              if (value === "projected_future_krw") return "이론 복리 곡선 (미래)";
              return "실제 자산";
            }}
            wrapperStyle={{ fontSize: 12, color: isDark ? "#d1d5db" : undefined }}
          />
          <Line
            type="monotone"
            dataKey="projected_krw"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="projected_future_krw"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            strokeDasharray="5 3"
          />
          <Line
            type="monotone"
            dataKey="actual_krw"
            stroke="#ef4444"
            strokeWidth={2}
            dot={{ r: 3, fill: "#ef4444", strokeWidth: 0 }}
            connectNulls={true}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
        파란선: 이론 복리 곡선 (점선=미래) / 빨간선: 실제 자산
        {!hasActualData && (
          <span className="ml-2 text-yellow-500">· 실제 자산 데이터가 없습니다. 계좌를 동기화하면 표시됩니다.</span>
        )}
      </p>
    </div>
  );
}
