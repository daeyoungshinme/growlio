import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchDRIPSimulation } from "@/api/dividends";
import { fmtKrwShort, fmtPct } from "@/utils/format";
import { useThemeStore } from "@/stores/themeStore";
import { chartTooltipStyle } from "@/utils/chart";

const YEARS_OPTIONS = [5, 10, 20, 30] as const;
type YearsOption = (typeof YEARS_OPTIONS)[number];

export default function DRIPSimulationChart() {
  const isDark = useThemeStore((s) => s.isDark);
  const [nYears, setNYears] = useState<YearsOption>(10);

  const { data, mutate, isPending } = useMutation({
    mutationFn: (years: number) => fetchDRIPSimulation({ n_years: years }),
  });

  const handleRun = (y: YearsOption) => {
    setNYears(y);
    mutate(y);
  };

  const tooltipStyle = chartTooltipStyle(isDark);

  const chartData =
    data?.yearly_points.map((p) => ({
      year: `${p.year}년`,
      drip: Math.round(p.portfolio_value_drip / 10000),
      cash: Math.round(p.portfolio_value_cash / 10000),
    })) ?? [];

  return (
    <div className="space-y-4">
      {/* 컨트롤 */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">시뮬레이션 기간</span>
        <div className="flex gap-1">
          {YEARS_OPTIONS.map((y) => (
            <button
              key={y}
              onClick={() => handleRun(y)}
              className={`px-3 py-1 text-xs rounded-lg font-medium transition-colors ${
                nYears === y
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
              }`}
            >
              {y}년
            </button>
          ))}
        </div>
        {!data && !isPending && (
          <button
            onClick={() => handleRun(nYears)}
            className="px-4 py-1.5 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            시뮬레이션 실행
          </button>
        )}
        {isPending && (
          <span className="flex items-center gap-1 text-xs text-gray-400">
            <Loader2 size={12} className="animate-spin" /> 계산 중...
          </span>
        )}
      </div>

      {data && (
        <>
          {/* 요약 뱃지 */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-green-50 dark:bg-green-900/20 rounded-xl p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">DRIP 최종 자산</p>
              <p className="text-base font-bold text-green-600 dark:text-green-400 mt-0.5">
                {fmtKrwShort(data.final_value_drip)}원
              </p>
            </div>
            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">현금수령 최종 자산</p>
              <p className="text-base font-bold text-gray-700 dark:text-gray-300 mt-0.5">
                {fmtKrwShort(data.final_value_cash)}원
              </p>
            </div>
            <div className="bg-blue-50 dark:bg-blue-900/20 rounded-xl p-3 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">DRIP 우위</p>
              <p className="text-base font-bold text-blue-600 dark:text-blue-400 mt-0.5">
                +{fmtPct(data.drip_advantage_pct)}
              </p>
            </div>
          </div>

          {/* 차트 */}
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={isDark ? "#374151" : "#f3f4f6"} />
                <XAxis dataKey="year" tick={{ fontSize: 10, fill: isDark ? "#9CA3AF" : "#6B7280" }} />
                <YAxis
                  tickFormatter={(v) => `${v}만`}
                  tick={{ fontSize: 10, fill: isDark ? "#9CA3AF" : "#6B7280" }}
                  width={50}
                />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    `${value.toLocaleString()}만원`,
                    name === "drip" ? "DRIP 재투자" : "현금 수령",
                  ]}
                  {...tooltipStyle}
                />
                <Area
                  type="monotone"
                  dataKey="drip"
                  stroke="#16A34A"
                  fill="#16A34A"
                  fillOpacity={0.15}
                  strokeWidth={2}
                  name="drip"
                />
                <Area
                  type="monotone"
                  dataKey="cash"
                  stroke="#6B7280"
                  fill="#6B7280"
                  fillOpacity={0.08}
                  strokeWidth={1.5}
                  strokeDasharray="4 2"
                  name="cash"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <p className="text-[11px] text-gray-400 dark:text-gray-500">{data.note}</p>
        </>
      )}

      {!data && !isPending && (
        <div className="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
          <p className="text-sm">기간을 선택하고 시뮬레이션을 실행하세요</p>
          <p className="text-xs mt-1">현재 포트폴리오 설정을 기반으로 계산됩니다</p>
        </div>
      )}
    </div>
  );
}
