import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend,
} from "recharts";
import { TrendingUp } from "lucide-react";
import { fetchDividendPlan } from "@/api/invest";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fmtKrw, fmtKrwShort } from "@/utils/format";
import { useThemeStore } from "@/stores/themeStore";
import { chartTooltipStyle } from "@/utils/chart";
import SkeletonCard from "@/components/common/SkeletonCard";

const MONTH_LABELS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"];

interface Props {
  onOpenSettings: () => void;
}

export default function DividendPlanSection({ onOpenSettings }: Props) {
  const { isDark } = useThemeStore();
  const tooltipStyle = chartTooltipStyle(isDark);

  const { data, isLoading, isError } = useQuery({
    queryKey: QUERY_KEYS.dividendPlan,
    queryFn: fetchDividendPlan,
    staleTime: STALE_TIME.MEDIUM,
  });

  if (isLoading) return <SkeletonCard rows={5} height="h-5" />;

  if (isError || !data) {
    return (
      <div className="card text-sm text-red-600 dark:text-red-400">
        배당 계획 데이터를 불러오지 못했습니다.
      </div>
    );
  }

  const {
    annual_dividend_goal,
    estimated_annual_krw,
    estimated_monthly_krw,
    actual_annual_received_krw,
    goal_achievement_pct,
    monthly_projected,
    monthly_received,
    yearly_received,
  } = data;

  // 월별 실수령 맵 (YYYY-MM → amount)
  const receivedByMonth: Record<number, number> = {};
  for (const r of monthly_received) {
    const monthNum = parseInt(r.month.split("-")[1], 10);
    receivedByMonth[monthNum] = (receivedByMonth[monthNum] ?? 0) + r.amount;
  }

  // 바차트 데이터: 예상 + 실수령 병합
  const monthlyChartData = monthly_projected.map((p) => ({
    name: MONTH_LABELS[p.month - 1],
    예상: p.amount_krw,
    실수령: receivedByMonth[p.month] ?? 0,
  }));

  // 평균 예상 배당금 (약한 달 판정용)
  const avgProjected =
    monthly_projected.reduce((s, p) => s + p.amount_krw, 0) / 12;

  const progressPct = goal_achievement_pct !== null ? Math.min(goal_achievement_pct, 100) : null;

  return (
    <div className="space-y-5">
      {/* 배당 목표 달성 카드 */}
      <div className="card">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-4">
          배당 목표 달성 현황
        </h3>

        {annual_dividend_goal ? (
          <>
            {/* 모바일: 달성률 히어로 + 보조 3열 */}
            <div className="sm:hidden mb-4">
              <div className="flex items-start justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-xl mb-3">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">배당 달성률</p>
                  <p className={`text-3xl font-bold ${(goal_achievement_pct ?? 0) >= 100 ? "text-red-500" : "text-blue-500"}`}>
                    {goal_achievement_pct !== null ? `${goal_achievement_pct.toFixed(1)}%` : "—"}
                  </p>
                  {(goal_achievement_pct ?? 0) >= 100 && (
                    <span className="inline-flex items-center gap-1 text-xs text-red-500 mt-0.5">
                      <TrendingUp size={12} /> 목표 달성
                    </span>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">목표</p>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                    {fmtKrw(annual_dividend_goal)}
                  </p>
                  <p className="text-xs text-gray-400 dark:text-gray-500">
                    월 {fmtKrw(annual_dividend_goal / 12)}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 leading-tight">예상 연배당</p>
                  <p className="text-sm font-bold text-red-500">{fmtKrw(estimated_annual_krw)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 leading-tight">월 평균</p>
                  <p className="text-sm font-bold text-gray-900 dark:text-gray-50">{fmtKrw(estimated_monthly_krw)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 leading-tight">올해 실수령</p>
                  <p className="text-sm font-bold text-gray-900 dark:text-gray-50">{fmtKrw(actual_annual_received_krw)}</p>
                </div>
              </div>
            </div>

            {/* 데스크탑: 기존 4열 */}
            <div className="hidden sm:grid sm:grid-cols-4 gap-4 mb-4">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">목표 연배당</p>
                <p className="text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(annual_dividend_goal)}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  월 {fmtKrw(annual_dividend_goal / 12)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">현재 예상 연배당</p>
                <p className="text-xl font-bold text-red-500">
                  {fmtKrw(estimated_annual_krw)}
                </p>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                  월 평균 {fmtKrw(estimated_monthly_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">올해 실수령</p>
                <p className="text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(actual_annual_received_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">달성률</p>
                <p className={`text-xl font-bold ${(goal_achievement_pct ?? 0) >= 100 ? "text-red-500" : "text-blue-500"}`}>
                  {goal_achievement_pct !== null ? `${goal_achievement_pct.toFixed(1)}%` : "—"}
                </p>
                {(goal_achievement_pct ?? 0) >= 100 && (
                  <span className="inline-flex items-center gap-1 text-xs text-red-500 mt-0.5">
                    <TrendingUp size={12} /> 목표 달성
                  </span>
                )}
              </div>
            </div>

            {progressPct !== null && (
              <div>
                <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
                  <span>0%</span>
                  <span>{goal_achievement_pct !== null ? `${goal_achievement_pct.toFixed(1)}%` : ""}</span>
                  <span>100%</span>
                </div>
                <div className="h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      progressPct >= 100 ? "bg-red-500" : "bg-blue-500"
                    }`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  목표까지 {fmtKrw(Math.max(0, annual_dividend_goal - estimated_annual_krw))} 부족
                </p>
              </div>
            )}
          </>
        ) : (
          <div className="py-2">
            <div className="flex items-center justify-between gap-3 p-3 bg-blue-50 dark:bg-blue-950 rounded-xl mb-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                배당 목표를 설정하면 달성률을 확인할 수 있습니다
              </p>
              <button
                onClick={onOpenSettings}
                className="shrink-0 px-3 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                목표 설정
              </button>
            </div>
            <div className="grid grid-cols-3 gap-3 sm:grid-cols-3">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">예상 연배당</p>
                <p className="text-base sm:text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(estimated_annual_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">예상 월평균</p>
                <p className="text-base sm:text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(estimated_monthly_krw)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">올해 실수령</p>
                <p className="text-base sm:text-xl font-bold text-gray-900 dark:text-gray-50">
                  {fmtKrw(actual_annual_received_krw)}
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 월별 배당 분포 */}
      <div className="card">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">
          월별 배당 분포
        </h3>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">
          예상 배당금 기준. 약한 달(평균 50% 미만)은 연한 색으로 표시.
        </p>
        <div className="h-[180px] sm:h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={monthlyChartData} margin={{ top: 0, right: 4, left: 0, bottom: 0 }}>
            <XAxis
              dataKey="name"
              tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#6b7280" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tickFormatter={(v: number) => fmtKrwShort(v)}
              tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#6b7280" }}
              axisLine={false}
              tickLine={false}
              width={50}
            />
            <Tooltip
              formatter={(v: number, name: string) => [fmtKrw(v), name]}
              contentStyle={tooltipStyle.contentStyle}
              labelStyle={tooltipStyle.labelStyle}
              itemStyle={tooltipStyle.itemStyle}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="예상" name="예상" radius={[3, 3, 0, 0]}>
              {monthlyChartData.map((_entry, i) => {
                const projected = monthly_projected[i]?.amount_krw ?? 0;
                const isWeak = avgProjected > 0 && projected < avgProjected * 0.5;
                return (
                  <Cell
                    key={`proj-${i}`}
                    fill={isWeak ? (isDark ? "#93c5fd" : "#bfdbfe") : (isDark ? "#3b82f6" : "#2563eb")}
                  />
                );
              })}
            </Bar>
            <Bar dataKey="실수령" name="실수령" fill={isDark ? "#6ee7b7" : "#10b981"} radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
        </div>
      </div>

      {/* 연도별 배당 추이 */}
      {yearly_received.length > 0 && (
        <div className="card">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-4">
            연도별 실수령 배당 추이
          </h3>
          <div className="h-[130px] sm:h-[160px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={yearly_received.map((y, i) => ({
                name: `${y.year}년`,
                배당: y.amount_krw,
                growth:
                  i > 0 && yearly_received[i - 1].amount_krw > 0
                    ? ((y.amount_krw - yearly_received[i - 1].amount_krw) /
                        yearly_received[i - 1].amount_krw) *
                      100
                    : null,
              }))}
              margin={{ top: 0, right: 4, left: 0, bottom: 0 }}
            >
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#6b7280" }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tickFormatter={(v: number) => fmtKrwShort(v)}
                tick={{ fontSize: 11, fill: isDark ? "#9ca3af" : "#6b7280" }}
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
              <Bar dataKey="배당" fill={isDark ? "#34d399" : "#059669"} radius={[3, 3, 0, 0]}>
                {yearly_received.map((_y, i) => (
                  <Cell key={`yr-${i}`} fill={isDark ? "#34d399" : "#059669"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap gap-3">
            {yearly_received.map((y, i) => {
              const prev = yearly_received[i - 1];
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
                    <span className={`ml-1 ${growth >= 0 ? "text-red-500" : "text-blue-500"}`}>
                      {growth >= 0 ? "+" : ""}
                      {growth.toFixed(1)}%
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
