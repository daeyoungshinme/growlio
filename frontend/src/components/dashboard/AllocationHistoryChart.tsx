import React, { memo, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useThemeStore } from "@/stores/themeStore";
import { fetchAllocationHistory } from "@/api/portfolios";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { chartTooltipStyle } from "@/utils/chart";
import { fmtKrw, fmtKrwShort, fmtMonth } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { REAL_ESTATE_ASSET_TYPE } from "@/constants/assets";

const TYPE_COLORS: Record<string, string> = {
  STOCK_DOMESTIC: "#2563EB",
  STOCK_FOREIGN: "#7C3AED",
  STOCK_KIS: "#2563EB",
  STOCK_KIWOOM: "#3B82F6",
  STOCK_OTHER: "#60A5FA",
  BANK_ACCOUNT: "#16A34A",
  DEPOSIT: "#4ADE80",
  [REAL_ESTATE_ASSET_TYPE]: "#D97706",
  CASH_OTHER: "#6B7280",
  CASH_STOCK: "#9CA3AF",
  OTHER: "#A855F7",
};

const DEFAULT_COLOR = "#94A3B8";

function AllocationHistoryChart() {
  const isDark = useThemeStore((s) => s.isDark);
  const [showDetail, setShowDetail] = useState(false);
  const [expandedMonth, setExpandedMonth] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.allocationHistory(12),
    queryFn: () => fetchAllocationHistory(12),
    staleTime: STALE_TIME.LONG,  // 1시간 — 백엔드 Redis TTL 1일에 맞게 조정
    gcTime: STALE_TIME.LONG,
  });

  const { chartData, allTypes } = useMemo(() => {
    if (!data || data.length === 0) return { chartData: [], allTypes: [] as string[] };

    const typeSet = new Set<string>();
    data.forEach((point) => point.allocations.forEach((a) => typeSet.add(a.asset_type)));
    const types = Array.from(typeSet);

    const points = data.map((point) => {
      const entry: Record<string, unknown> = {
        month: point.month.slice(2, 7).replace("-", "."),
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

  const reversedMonthly = useMemo(() => {
    if (!data || data.length === 0) return [];
    return [...data].reverse();
  }, [data]);

  const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(isDark);

  if (isLoading) {
    return (
      <div className="card">
        <div className="h-4 w-40 bg-gray-100 dark:bg-gray-800 rounded animate-pulse mb-4" />
        <div className="h-52 bg-gray-50 dark:bg-gray-800 rounded animate-pulse" />
      </div>
    );
  }

  if (!chartData.length) return null;

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">
          자산 추이 (최근 12개월)
        </h2>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={isDark ? "#374151" : "#F3F4F6"}
            vertical={false}
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
            cursor={{ fill: isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.04)" }}
            formatter={(value: number, key: string) => [fmtKrwShort(value), labelMap[key] ?? key]}
          />
          <Legend
            formatter={(value: string) => labelMap[value] ?? value}
            wrapperStyle={{ fontSize: 11 }}
          />
          {allTypes.map((type, idx) => (
            <Bar
              key={type}
              dataKey={type}
              stackId="1"
              fill={TYPE_COLORS[type] ?? DEFAULT_COLOR}
              radius={idx === allTypes.length - 1 ? [3, 3, 0, 0] : undefined}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>

      <button
        onClick={() => setShowDetail((v) => !v)}
        className="mt-4 w-full flex items-center justify-between py-2 px-3 text-xs text-gray-400 dark:text-gray-500 font-medium hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors"
      >
        <span>월별 상세</span>
        <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${showDetail ? "rotate-180" : ""}`} />
      </button>

      {showDetail && (
        <div className="mt-2 max-h-96 overflow-y-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-white dark:bg-gray-900">
              <tr className="border-b border-gray-100 dark:border-gray-700">
                <th className="py-1.5 px-2 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">월</th>
                <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">자산 합계</th>
                <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">전월 대비</th>
                <th className="py-1.5 px-1 w-6" />
              </tr>
            </thead>
            <tbody>
              {reversedMonthly.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-gray-300 dark:text-gray-600 text-xs">데이터 없음</td>
                </tr>
              ) : (
                reversedMonthly.map((row, i, arr) => {
                  const prev = arr[i + 1];
                  const change = prev && prev.total_krw > 0
                    ? ((row.total_krw - prev.total_krw) / prev.total_krw) * 100
                    : null;
                  const isExpanded = expandedMonth === row.month;
                  return (
                    <React.Fragment key={row.month}>
                      <tr
                        onClick={() => setExpandedMonth(isExpanded ? null : row.month)}
                        className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                      >
                        <td className="py-2 px-2 text-xs text-gray-800 dark:text-gray-200">{fmtMonth(row.month)}</td>
                        <td className="py-2 px-2 text-xs text-right font-medium text-gray-900 dark:text-gray-50">
                          {fmtKrw(row.total_krw)}
                        </td>
                        <td className="py-2 px-2 text-xs text-right">
                          {change != null ? (
                            <span className={`${pnlColor(change)} font-medium`}>
                              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                            </span>
                          ) : (
                            <span className="text-gray-300 dark:text-gray-600">—</span>
                          )}
                        </td>
                        <td className="py-2 px-1 text-gray-400 dark:text-gray-500">
                          <ChevronRight className={`w-3.5 h-3.5 transition-transform duration-200 ${isExpanded ? "rotate-90" : ""}`} />
                        </td>
                      </tr>
                      {isExpanded && row.allocations.length > 0 && (
                        <tr key={`${row.month}-detail`} className="border-b border-gray-50 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
                          <td colSpan={4} className="px-3 pt-2 pb-3">
                            <div className="space-y-1.5 pl-2 border-l-2 border-gray-200 dark:border-gray-600 ml-1">
                              {[...row.allocations]
                                .sort((a, b) => b.amount_krw - a.amount_krw)
                                .map((alloc) => (
                                  <div key={alloc.asset_type} className="flex items-center justify-between gap-2 text-xs">
                                    <div className="flex items-center gap-1.5">
                                      <span
                                        className="w-2 h-2 rounded-full flex-shrink-0"
                                        style={{ backgroundColor: TYPE_COLORS[alloc.asset_type] ?? DEFAULT_COLOR }}
                                      />
                                      <span className="text-gray-500 dark:text-gray-400">{alloc.label}</span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                      <span className="text-gray-700 dark:text-gray-200 font-medium">{fmtKrw(alloc.amount_krw)}</span>
                                      <span className="text-gray-400 dark:text-gray-500 w-11 text-right">{alloc.weight_pct.toFixed(1)}%</span>
                                    </div>
                                  </div>
                                ))}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default memo(AllocationHistoryChart);
