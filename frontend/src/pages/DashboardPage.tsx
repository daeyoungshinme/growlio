import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { fetchDashboard, fetchDividendByTicker, fetchExchangeRate } from "../api/dashboard";
import { fmtKrw, fmtMonth, fmtPct } from "../utils/format";
import DividendSection from "../components/dashboard/DividendSection";
import MonthlyTrendChart from "../components/trend/MonthlyTrendChart";
import PortfolioSummaryCard from "../components/dashboard/PortfolioSummaryCard";
import AssetAllocationChart from "../components/dashboard/AssetAllocationChart";
import { ASSET_TYPE_LABELS } from "../constants";
import type { PortfolioOverview } from "../types";

const fetchOverviewSummary = () =>
  api.get<PortfolioOverview>("/portfolio/overview").then((r) => r.data);


export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: fetchDashboard,
    refetchInterval: 60_000,
  });

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["portfolio-overview"],
    queryFn: fetchOverviewSummary,
    refetchInterval: 60_000,
  });

  const { data: tickerDividends, isLoading: tickerDividendsLoading } = useQuery({
    queryKey: ["dividend-by-ticker"],
    queryFn: fetchDividendByTicker,
    staleTime: 5 * 60 * 1000,
    refetchInterval: false,
  });

  const { data: exchangeRate } = useQuery({
    queryKey: ["exchange-rate"],
    queryFn: fetchExchangeRate,
    staleTime: 5 * 60 * 1000,
    refetchInterval: 5 * 60 * 1000,
  });

  const allocationChartData = useMemo(() => {
    if (!data) return [];
    const stockItems = data.asset_allocation.filter((item) => item.type.startsWith("STOCK_"));
    const nonStockItems = data.asset_allocation.filter((item) => !item.type.startsWith("STOCK_"));
    const result = nonStockItems.map((item) => ({
      name: ASSET_TYPE_LABELS[item.type] ?? item.type,
      value: item.amount_krw,
      pct: item.pct,
    }));
    if (stockItems.length > 0) {
      result.unshift({
        name: "주식",
        value: stockItems.reduce((sum, item) => sum + item.amount_krw, 0),
        pct: stockItems.reduce((sum, item) => sum + item.pct, 0),
      });
    }
    return result;
  }, [data]);

  if (isLoading) return <div className="flex items-center justify-center h-64 text-gray-400 dark:text-gray-500">로딩 중...</div>;
  if (error || !data) return <div className="text-red-500">데이터를 불러오지 못했습니다</div>;

  const currentYear = new Date().getFullYear();
  const retirementLabel = data.retirement_target_year
    ? `${data.retirement_target_year}년 (${data.retirement_target_year - currentYear}년 후)`
    : "미설정";

  const depositColor =
    data.deposit_achievement_pct != null && data.deposit_achievement_pct >= 100
      ? "text-green-600"
      : "text-blue-600 dark:text-blue-400";

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">대시보드</h1>

      {/* Row 1: Hero Card — 자산 현황 + 핵심 지표 통합 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 flex flex-col lg:flex-row gap-6">
        {/* 좌측: 자산 총액 + 누적 수익률 + 3개 미니 지표 */}
        <div className="flex-1 flex flex-col justify-between">
          <div className="flex flex-col gap-4">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">전체 자산</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-gray-50 mt-1">
                {data.total_assets_krw.toLocaleString()}원
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">누적 수익률</p>
              <p className={`text-2xl font-bold mt-0.5 ${
                data.cumulative_return_pct == null
                  ? "text-gray-400 dark:text-gray-500"
                  : data.cumulative_return_pct >= 0
                  ? "text-red-500"
                  : "text-blue-500"
              }`}>
                {fmtPct(data.cumulative_return_pct)}
              </p>
            </div>
          </div>
          <div className="border-t border-gray-100 dark:border-gray-700 mt-4 pt-4 grid grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">목표 수익률</p>
              <p className="text-sm font-semibold text-purple-600 dark:text-purple-400 mt-0.5">
                {data.goal_annual_return_pct != null ? `${data.goal_annual_return_pct}%` : "미설정"}
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">연간 목표</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">입금 달성률</p>
              <p className={`text-sm font-semibold mt-0.5 ${depositColor}`}>
                {data.deposit_achievement_pct != null
                  ? `${data.deposit_achievement_pct.toFixed(1)}%`
                  : "목표 미설정"}
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                {data.annual_deposit_goal != null
                  ? `목표 ${(data.annual_deposit_goal / 1e4).toFixed(0)}만원`
                  : "목표 미설정"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">은퇴 목표</p>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">{retirementLabel}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                {data.retirement_target_year ? "은퇴 목표 연도" : "미설정"}
              </p>
            </div>
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">USD/KRW</p>
              <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 mt-0.5">
                {exchangeRate ? Math.round(exchangeRate.usd_krw).toLocaleString() + "원" : "—"}
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">기준환율</p>
            </div>
          </div>
        </div>
        {/* 우측: 자산 비중 도넛 차트 */}
        <div className="lg:w-72 shrink-0">
          {allocationChartData.length > 0 ? (
            <AssetAllocationChart data={allocationChartData} />
          ) : (
            <div className="flex items-center justify-center h-40 text-gray-300 dark:text-gray-600 text-sm">
              자산 데이터 없음
            </div>
          )}
        </div>
      </div>

      {/* Row 2: 포트폴리오 요약 + 배당 현황 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">주식 포트폴리오 요약</h2>
            <Link
              to="/portfolio"
              className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              전체 보기 <ArrowRight size={14} />
            </Link>
          </div>
          <PortfolioSummaryCard
            overview={overview}
            isLoading={overviewLoading}
            stockAllocation={overview?.stock_allocation}
          />
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">배당 현황</h2>
          <DividendSection
            annualReceived={data.annual_dividends_received ?? null}
            estimatedAnnual={data.estimated_annual_dividends ?? null}
            monthlyBreakdown={data.dividend_monthly_breakdown ?? []}
            tickerItems={tickerDividends}
            tickerItemsLoading={tickerDividendsLoading}
          />
        </div>
      </div>

      {/* Row 3: 월별 자산 추이 + 월별 상세 테이블 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">월별 자산 추이 (최근 12개월)</h2>
          <MonthlyTrendChart data={data.monthly_trend} />
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">월별 상세</h2>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full">
              <thead className="sticky top-0 bg-white dark:bg-gray-900">
                <tr className="border-b border-gray-100 dark:border-gray-700">
                  <th className="py-2 px-3 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">월</th>
                  <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">자산 합계</th>
                  <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">전월 대비</th>
                </tr>
              </thead>
              <tbody>
                {data.monthly_trend.length === 0 ? (
                  <tr><td colSpan={3} className="py-8 text-center text-gray-300 dark:text-gray-600 text-sm">데이터 없음</td></tr>
                ) : (
                  [...data.monthly_trend].reverse().map((row, i, arr) => {
                    const prev = arr[i + 1];
                    const change = prev ? ((row.total_krw - prev.total_krw) / prev.total_krw) * 100 : null;
                    return (
                      <tr key={row.month} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                        <td className="py-2.5 px-3 text-sm text-gray-700 dark:text-gray-300">{fmtMonth(row.month)}</td>
                        <td className="py-2.5 px-3 text-sm text-right font-medium text-gray-900 dark:text-gray-50">
                          {fmtKrw(row.total_krw)}
                        </td>
                        <td className="py-2.5 px-3 text-sm text-right">
                          {change != null ? (
                            <span className={change >= 0 ? "text-red-500 font-medium" : "text-blue-500 font-medium"}>
                              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                            </span>
                          ) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
