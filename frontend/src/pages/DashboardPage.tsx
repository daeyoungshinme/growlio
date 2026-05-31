import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, TrendingDown, TrendingUp, Wallet } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { fetchAccounts } from "../api/assets";
import { fetchDashboard } from "../api/dashboard";
import { fetchDCAAnalysis } from "../api/invest";
import { useExchangeRate } from "../hooks/useExchangeRate";
import { fmtKrw, fmtMonth, fmtPct } from "../utils/format";
import DividendSection from "../components/dashboard/DividendSection";
import MonthlyTrendChart from "../components/trend/MonthlyTrendChart";
import PortfolioSummaryCard from "../components/dashboard/PortfolioSummaryCard";
import AssetAllocationChart from "../components/dashboard/AssetAllocationChart";
import SkeletonCard from "../components/common/SkeletonCard";
import SkeletonStatBox from "../components/common/SkeletonStatBox";
import { ASSET_TYPE_LABELS } from "../constants";
import { pnlColor, PROFIT_COLOR, LOSS_COLOR } from "../utils/colors";
import { STALE_TIME, REFETCH_INTERVAL } from "../constants/queryConfig";
import { QUERY_KEYS } from "../constants/queryKeys";
import type { PortfolioOverview } from "../types";

const fetchOverviewSummary = () =>
  api.get<PortfolioOverview>("/portfolio/overview").then((r) => r.data);

export default function DashboardPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [showMonthlyDetail, setShowMonthlyDetail] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: QUERY_KEYS.dashboard,
    queryFn: fetchDashboard,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
    refetchOnWindowFocus: true,
  });

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverview,
    queryFn: fetchOverviewSummary,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
    refetchOnWindowFocus: true,
  });

  const { data: dcaData } = useQuery({
    queryKey: QUERY_KEYS.investDca,
    queryFn: fetchDCAAnalysis,
    staleTime: STALE_TIME.MEDIUM,
    refetchInterval: REFETCH_INTERVAL.DASHBOARD,
  });

  const { data: accounts = [], isLoading: accountsLoading } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });

  const exchangeRate = useExchangeRate();

  const overallDividendYield = useMemo(() => {
    const estimated = data?.estimated_annual_dividends;
    const invested = overview?.total_invested_krw;
    if (estimated && invested && invested > 0) return (estimated / invested) * 100;
    return null;
  }, [data?.estimated_annual_dividends, overview?.total_invested_krw]);

  const allocationChartData = useMemo(() => {
    if (!data) return [];
    const CASH_TYPES = new Set(["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER", "CASH_STOCK"]);
    const stockItems = data.asset_allocation.filter((item) => item.type.startsWith("STOCK_"));
    const cashItems = data.asset_allocation.filter((item) => CASH_TYPES.has(item.type));
    const otherItems = data.asset_allocation.filter(
      (item) => !item.type.startsWith("STOCK_") && !CASH_TYPES.has(item.type)
    );
    const result = otherItems.map((item) => ({
      name: ASSET_TYPE_LABELS[item.type] ?? item.type,
      value: item.amount_krw,
      pct: item.pct,
    }));
    if (cashItems.length > 0) {
      result.unshift({
        name: "현금",
        value: cashItems.reduce((sum, item) => sum + item.amount_krw, 0),
        pct: cashItems.reduce((sum, item) => sum + item.pct, 0),
      });
    }
    if (stockItems.length > 0) {
      result.unshift({
        name: "주식",
        value: stockItems.reduce((sum, item) => sum + item.amount_krw, 0),
        pct: stockItems.reduce((sum, item) => sum + item.pct, 0),
      });
    }
    return result;
  }, [data]);

  if (isLoading || accountsLoading) return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex divide-x divide-gray-100 dark:divide-gray-700">
          {[0, 1, 2, 3].map((i) => <SkeletonStatBox key={i} />)}
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SkeletonCard rows={4} height="h-5" />
        <SkeletonCard rows={4} height="h-5" />
      </div>
      <SkeletonCard rows={3} height="h-4" />
    </div>
  );
  if (error || !data) return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <p className="text-sm text-red-500">데이터를 불러오지 못했습니다</p>
      <button
        onClick={() => qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard })}
        className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
      >
        다시 시도
      </button>
    </div>
  );

  if (accounts.length === 0) return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-12 text-center max-w-md w-full">
        <Wallet size={48} className="mx-auto mb-4 text-gray-300 dark:text-gray-600" />
        <h2 className="text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2">
          등록된 자산이 없습니다
        </h2>
        <p className="text-sm text-gray-400 dark:text-gray-500 mb-6">
          자산관리에서 계좌를 등록하면<br />대시보드에서 자산 현황을 확인할 수 있습니다.
        </p>
        <button
          onClick={() => navigate("/asset-management")}
          className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          자산관리로 이동
        </button>
      </div>
    </div>
  );

  const currentYear = new Date().getFullYear();

  const depositColor =
    data.deposit_achievement_pct != null && data.deposit_achievement_pct >= 100
      ? "text-green-600"
      : "text-blue-600 dark:text-blue-400";

  const timeline = dcaData?.goal_timeline;
  const currentProgressPct = timeline?.current_progress_pct ?? data.goal_achievement_pct;
  const progressColor =
    currentProgressPct == null
      ? "text-gray-400 dark:text-gray-500"
      : currentProgressPct >= 100
      ? "text-red-500"
      : currentProgressPct >= 80
      ? "text-orange-500"
      : "text-gray-600 dark:text-gray-300";

  const goalAmountDisplay = dcaData?.settings.goal_amount ?? data.goal_amount;


  return (
    <div className="space-y-6">
      {/* Row 1: Hero Card — 자산 현황 + 핵심 지표 통합 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 flex flex-col gap-3 lg:gap-4">
        <div className="flex flex-row gap-3 lg:gap-6">
        {/* 좌측: 자산 총액 + 누적 수익률 + 3개 미니 지표 */}
        <div className="flex-1 min-w-0 flex flex-col justify-between">
          <div className="flex flex-col gap-4">
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">전체 자산</p>
              <p className="text-3xl sm:text-4xl lg:text-5xl font-bold text-gray-900 dark:text-gray-50 mt-1">
                {fmtKrw(Math.floor(data.total_assets_krw))}
              </p>
              <p className="text-sm text-gray-400 dark:text-gray-500 mt-0.5">
                {Math.floor(data.total_assets_krw).toLocaleString()}원
              </p>
            </div>
            <div className="flex items-start gap-6">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">누적 수익률</p>
                <p className={`text-lg sm:text-xl font-bold mt-0.5 ${
                  data.cumulative_return_pct == null
                    ? "text-gray-400 dark:text-gray-500"
                    : pnlColor(data.cumulative_return_pct)
                }`}>
                  {fmtPct(data.cumulative_return_pct)}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">환율(USD/KRW)</p>
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 mt-0.5">
                  {exchangeRate ? Math.round(exchangeRate).toLocaleString() + "원" : "—"}
                </p>
              </div>
            </div>
          </div>
          {/* 보조 항목: 입금 달성률 · 은퇴 목표 */}
          <div className="border-t border-gray-100 dark:border-gray-700 mt-4 pt-4">
            <div className="grid grid-cols-2 gap-2 sm:gap-4">
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium truncate">입금 달성률</p>
                <p className={`text-sm font-semibold mt-0.5 ${depositColor}`}>
                  {data.deposit_achievement_pct != null ? `${data.deposit_achievement_pct.toFixed(1)}%` : "목표 미설정"}
                </p>
                {data.annual_deposit_goal != null && (
                  <p className="text-xs text-gray-300 dark:text-gray-600 truncate mt-0.5">목표 {fmtKrw(data.annual_deposit_goal)}</p>
                )}
              </div>
              <div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">은퇴 목표</p>
                {data.retirement_target_year ? (
                  <>
                    <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">
                      {data.retirement_target_year}년
                    </p>
                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      {data.retirement_target_year - currentYear}년 후
                    </p>
                  </>
                ) : (
                  <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">미설정</p>
                )}
              </div>
            </div>
          </div>
        </div>
        {/* 모바일: 컴팩트 도넛 차트 (우측 고정) */}
        <div className="lg:hidden w-32 sm:w-40 shrink-0">
          {allocationChartData.length > 0 ? (
            <AssetAllocationChart data={allocationChartData} compact />
          ) : (
            <div className="flex items-center justify-center h-32 text-gray-300 dark:text-gray-600 text-xs text-center">
              자산<br />없음
            </div>
          )}
        </div>
        {/* 데스크탑: 풀사이즈 도넛 차트 */}
        <div className="hidden lg:block lg:w-[460px] shrink-0">
          {allocationChartData.length > 0 ? (
            <AssetAllocationChart data={allocationChartData} />
          ) : (
            <div className="flex items-center justify-center h-40 text-gray-300 dark:text-gray-600 text-sm">
              자산 데이터 없음
            </div>
          )}
        </div>
        </div>
        {/* 목표 달성 전망 */}
        <div className="border-t border-gray-100 dark:border-gray-700 pt-3 space-y-3">
          <div className="grid grid-cols-3 gap-4">
            {/* 현재 진행율 */}
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">현재 진행율</p>
              <p className={`text-sm sm:text-base lg:text-lg font-bold ${progressColor}`}>
                {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
              </p>
              {goalAmountDisplay != null && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">목표 {fmtKrw(goalAmountDisplay)}</p>
              )}
            </div>
            {/* 목표 달성 예상 */}
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">목표 달성 예상</p>
              <p className="text-sm sm:text-base lg:text-lg font-bold text-gray-900 dark:text-gray-50">
                {timeline?.expected_goal_date ? fmtMonth(timeline.expected_goal_date) : "—"}
              </p>
              {timeline?.months_to_goal != null && (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">약 {timeline.months_to_goal}개월 후</p>
              )}
            </div>
            {/* 계획 대비 */}
            <div>
              <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">계획 대비</p>
              {timeline?.lead_lag_months == null ? (
                <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">—</p>
              ) : timeline.lead_lag_months > 0 ? (
                <span className="flex flex-col gap-0.5 mt-1">
                  <span className={`text-xs font-medium ${PROFIT_COLOR} flex items-center gap-1`}>
                    <TrendingUp size={12} />{timeline.lead_lag_months}개월 앞서
                  </span>
                  {timeline.actual_expected_goal_date && (
                    <span className="text-xs text-red-400 whitespace-nowrap">{fmtMonth(timeline.actual_expected_goal_date)} 달성 예상</span>
                  )}
                </span>
              ) : timeline.lead_lag_months < 0 ? (
                <span className="flex flex-col gap-0.5 mt-1">
                  <span className={`text-xs font-medium ${LOSS_COLOR} flex items-center gap-1`}>
                    <TrendingDown size={12} />{Math.abs(timeline.lead_lag_months)}개월 지연
                  </span>
                  {timeline.actual_expected_goal_date && (
                    <span className="text-xs text-blue-400 whitespace-nowrap">{fmtMonth(timeline.actual_expected_goal_date)} 달성 예상</span>
                  )}
                </span>
              ) : (
                <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1">계획과 일치</p>
              )}
            </div>
          </div>
          {/* 진행 바 */}
          {currentProgressPct != null && (
            <div>
              <div className="flex justify-between text-xs text-gray-400 dark:text-gray-500 mb-1">
                <span>0%</span>
                <span>100%</span>
              </div>
              <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-blue-500 rounded-full transition-all"
                  style={{ width: `${Math.min(currentProgressPct, 100)}%` }}
                />
              </div>
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
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="flex items-center justify-between px-5 pt-4 pb-2">
            <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">배당 현황</h2>
            <Link
              to="/portfolio?tab=배당+현황"
              className="flex items-center gap-1 text-sm text-blue-600 dark:text-blue-400 hover:underline"
            >
              자세히 보기 <ArrowRight size={14} />
            </Link>
          </div>
          <DividendSection
            annualReceived={data.annual_dividends_received ?? null}
            estimatedAnnual={data.estimated_annual_dividends ?? null}
            estimatedMonthly={
              data.estimated_annual_dividends != null
                ? Math.round(data.estimated_annual_dividends / 12)
                : null
            }
            overallDividendYield={overallDividendYield}
          />
        </div>
      </div>

      {/* Row 3: 월별 자산 추이 */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">월별 자산 추이 (최근 12개월)</h2>
        <MonthlyTrendChart data={data.monthly_trend ?? []} />
        <button
          onClick={() => setShowMonthlyDetail((v) => !v)}
          className="mt-4 w-full flex items-center justify-between py-2 px-3 text-xs text-gray-400 dark:text-gray-500 font-medium hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors"
        >
          <span>월별 상세</span>
          <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${showMonthlyDetail ? "rotate-180" : ""}`} />
        </button>
        {showMonthlyDetail && (
          <div className="mt-2 max-h-72 overflow-y-auto">
            <table className="w-full">
              <thead className="sticky top-0 bg-white dark:bg-gray-900">
                <tr className="border-b border-gray-100 dark:border-gray-700">
                  <th className="py-1.5 px-2 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">월</th>
                  <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">자산 합계</th>
                  <th className="py-1.5 px-2 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">전월 대비</th>
                </tr>
              </thead>
              <tbody>
                {(data.monthly_trend ?? []).length === 0 ? (
                  <tr><td colSpan={3} className="py-8 text-center text-gray-300 dark:text-gray-600 text-xs">데이터 없음</td></tr>
                ) : (
                  [...(data.monthly_trend ?? [])].reverse().map((row, i, arr) => {
                    const prev = arr[i + 1];
                    const change = prev ? ((row.total_krw - prev.total_krw) / prev.total_krw) * 100 : null;
                    return (
                      <tr key={row.month} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                        <td className="py-2 px-2 text-xs text-gray-800 dark:text-gray-200">{fmtMonth(row.month)}</td>
                        <td className="py-2 px-2 text-xs text-right font-medium text-gray-900 dark:text-gray-50">
                          {fmtKrw(row.total_krw)}
                        </td>
                        <td className="py-2 px-2 text-xs text-right">
                          {change != null ? (
                            <span className={`${pnlColor(change)} font-medium`}>
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
        )}
      </div>
    </div>
  );
}
