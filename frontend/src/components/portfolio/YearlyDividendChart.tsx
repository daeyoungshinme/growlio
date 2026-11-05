import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { fetchDividendPlan } from "@/api/invest";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { useThemeStore } from "@/stores/themeStore";
import { chartTickStyle, chartTooltipStyle } from "@/utils/chart";
import { summarizeAmounts } from "@/utils/chartSummary";
import { pnlColor } from "@/utils/colors";
import { fmtKrw, fmtKrwShort, fmtPct } from "@/utils/format";

/** 연도별 실수령 배당 — 계좌 필터와 무관한 전체 계좌 합계라 화면에 기준을 표시한다 */
export default function YearlyDividendChart() {
  const { isDark } = useThemeStore();
  const tooltipStyle = chartTooltipStyle(isDark);
  const { data } = useQuery({
    queryKey: QUERY_KEYS.dividendPlan,
    queryFn: fetchDividendPlan,
    staleTime: STALE_TIME.MEDIUM,
  });
  const years = data?.yearly_received ?? [];
  if (years.length === 0) return null;

  return (
    <div className="card">
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">
        연도별 실수령 배당 추이
      </h3>
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">전체 계좌 기준</p>
      <div
        className="h-[130px] sm:h-[160px]"
        role="img"
        aria-label={summarizeAmounts(
          "연도별 실수령 배당 차트",
          years.map((y) => ({ name: `${y.year}년`, amount: y.amount_krw })),
        )}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={years.map((y) => ({ name: `${y.year}년`, 배당: y.amount_krw }))}
            margin={{ top: 0, right: 4, left: 0, bottom: 0 }}
          >
            <XAxis dataKey="name" tick={chartTickStyle(isDark)} axisLine={false} tickLine={false} />
            <YAxis
              tickFormatter={(v: number) => fmtKrwShort(v)}
              tick={chartTickStyle(isDark)}
              axisLine={false}
              tickLine={false}
              width={50}
            />
            <Tooltip
              formatter={(v: number) => [fmtKrw(v), "실수령 배당"]}
              contentStyle={tooltipStyle.contentStyle}
              labelStyle={tooltipStyle.labelStyle}
              itemStyle={tooltipStyle.itemStyle}
            />
            <Bar dataKey="배당" fill={isDark ? "#34d399" : "#059669"} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap gap-3">
        {years.map((y, i) => {
          const prev = years[i - 1];
          const growth =
            prev && prev.amount_krw > 0
              ? ((y.amount_krw - prev.amount_krw) / prev.amount_krw) * 100
              : null;
          return (
            <div key={y.year} className="text-xs">
              <span className="text-gray-500 dark:text-gray-400">{y.year}년 </span>
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {fmtKrw(y.amount_krw)}
              </span>
              {growth !== null && (
                <span className={`ml-1 ${pnlColor(growth)}`}>{fmtPct(growth, 1)}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
