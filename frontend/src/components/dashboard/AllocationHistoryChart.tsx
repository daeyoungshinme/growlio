import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { fetchAllocationHistory } from "../../api/portfolios";
import { QUERY_KEYS } from "../../constants/queryKeys";
import { STALE_TIME } from "../../constants/queryConfig";
import { chartTooltipStyle } from "../../utils/chart";
import { fmtKrwShort } from "../../utils/format";

// 자산 유형별 색상 — AssetAllocationChart의 COLORS와 다른 팔레트로 구분
const TYPE_COLORS: Record<string, string> = {
  STOCK_KIS: "#2563EB",
  STOCK_KIWOOM: "#3B82F6",
  STOCK_OTHER: "#60A5FA",
  BANK_ACCOUNT: "#16A34A",
  DEPOSIT: "#4ADE80",
  REAL_ESTATE: "#D97706",
  CASH_OTHER: "#6B7280",
  CASH_STOCK: "#9CA3AF",
  OTHER: "#A855F7",
};

const DEFAULT_COLOR = "#94A3B8";

export default function AllocationHistoryChart() {
  const isDark = useThemeStore((s) => s.isDark);
  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.allocationHistory(12),
    queryFn: () => fetchAllocationHistory(12),
    staleTime: STALE_TIME.MEDIUM,
  });

  // Recharts AreaChart용 데이터 변환
  const { chartData, allTypes } = useMemo(() => {
    if (!data || data.length === 0) return { chartData: [], allTypes: [] as string[] };

    const typeSet = new Set<string>();
    data.forEach((point) => point.allocations.forEach((a) => typeSet.add(a.asset_type)));
    const types = Array.from(typeSet);

    const points = data.map((point) => {
      const entry: Record<string, unknown> = {
        month: point.month.slice(2).replace("-", "."), // "2026-06" → "26.6"
      };
      const byType = Object.fromEntries(point.allocations.map((a) => [a.asset_type, a.amount_krw]));
      types.forEach((t) => {
        entry[t] = byType[t] ?? 0;
      });
      return entry;
    });

    return { chartData: points, allTypes: types };
  }, [data]);

  const labelMap = useMemo(() => {
    if (!data || data.length === 0) return {} as Record<string, string>;
    const map: Record<string, string> = {};
    data.forEach((point) => point.allocations.forEach((a) => { map[a.asset_type] = a.label; }));
    return map;
  }, [data]);

  const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(isDark);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="h-4 w-40 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mb-4" />
        <div className="h-52 bg-gray-50 dark:bg-gray-800 rounded animate-pulse" />
      </div>
    );
  }

  if (!chartData.length) return null;

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">
        자산 배분 추이 (최근 12개월)
      </h2>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={isDark ? "#374151" : "#F3F4F6"}
          />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6B7280" }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tickFormatter={(v: number) => fmtKrwShort(v)}
            tick={{ fontSize: 11, fill: isDark ? "#9CA3AF" : "#6B7280" }}
            tickLine={false}
            axisLine={false}
            width={52}
          />
          <Tooltip
            contentStyle={contentStyle}
            labelStyle={labelStyle}
            itemStyle={itemStyle}
            formatter={(value: number, key: string) => [
              fmtKrwShort(value),
              labelMap[key] ?? key,
            ]}
          />
          <Legend
            formatter={(value: string) => labelMap[value] ?? value}
            wrapperStyle={{ fontSize: 11 }}
          />
          {allTypes.map((type) => (
            <Area
              key={type}
              type="monotone"
              dataKey={type}
              stackId="1"
              stroke={TYPE_COLORS[type] ?? DEFAULT_COLOR}
              fill={TYPE_COLORS[type] ?? DEFAULT_COLOR}
              fillOpacity={isDark ? 0.6 : 0.7}
              strokeWidth={1.5}
              dot={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
