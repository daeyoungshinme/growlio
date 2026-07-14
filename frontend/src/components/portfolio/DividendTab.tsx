import { lazy, Suspense, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useThemeStore } from "@/stores/themeStore";
import { fmtKrwShort } from "@/utils/format";
import SkeletonCard from "@/components/common/SkeletonCard";

const TreemapChart = lazy(() => import("./TreemapChart"));
const MonthlyDividendChart = lazy(() => import("./MonthlyDividendChart"));
import MonthlyTickerDetail from "./MonthlyTickerDetail";
import MonthlyOptimizationCard from "./MonthlyOptimizationCard";
import type { DividendByTicker, DividendYield } from "@/types";
import {
  MONTH_LABELS,
  dividendFreqInfo,
  weightBarColor,
  yieldBadgeClass,
} from "@/utils/dividendUtils";
import EmptyState from "@/components/common/EmptyState";

interface DividendSummary {
  annual_received: number;
  estimated_annual: number;
  monthly_breakdown: { month: string; amount: number }[];
  monthly_ticker_breakdown: { month: string; ticker: string | null; amount: number }[];
}

interface Props {
  dividendData: DividendYield[];
  divLoading: boolean;
  divSummary: DividendSummary | undefined;
  dividendByTicker: DividendByTicker[];
  totalInvestedKrw?: number;
}

const DIV_SUBTABS = ["종목별 배당", "월별 배당"] as const;
type DivSubTab = (typeof DIV_SUBTABS)[number];

export default function DividendTab({
  dividendData,
  divLoading: _divLoading,
  divSummary,
  dividendByTicker,
  totalInvestedKrw,
}: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const [divSubTab, setDivSubTab] = useState<DivSubTab>("종목별 배당");
  const [selectedMonth, setSelectedMonth] = useState<number>(new Date().getMonth() + 1);

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

  const positionsDivMap = useMemo(
    () => Object.fromEntries(dividendData.map((d) => [`${d.ticker}-${d.market}`, d])),
    [dividendData],
  );

  const tickerOnlyDivMap = useMemo(() => {
    const map: Record<string, DividendYield> = {};
    for (const d of dividendData) {
      const existing = map[d.ticker];
      if (!existing || d.investment_yield > existing.investment_yield) map[d.ticker] = d;
    }
    return map;
  }, [dividendData]);

  const totalEstimated = dividendByTicker.reduce((s, d) => s + d.estimated_annual_krw, 0);
  const estimatedMonthly = dividendByTicker.reduce((s, d) => s + d.estimated_monthly_krw, 0);
  const received = divSummary?.annual_received ?? 0;

  const overallDividendYield =
    totalInvestedKrw && totalInvestedKrw > 0 && totalEstimated > 0
      ? (totalEstimated / totalInvestedKrw) * 100
      : null;

  const dividendChartData = useMemo(
    () =>
      dividendByTicker
        .filter((d) => d.estimated_annual_krw > 0)
        .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw)
        .map((d) => ({
          name: d.name,
          ticker: d.ticker ?? undefined,
          value: d.estimated_annual_krw,
          pct: totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0,
        })),
    [dividendByTicker, totalEstimated],
  );

  // 종목별 배당 테이블용 (모바일/데스크탑 공용) — 중복 sort 제거
  const sortedByTicker = useMemo(
    () =>
      dividendByTicker
        .filter((d) => d.estimated_annual_krw > 0)
        .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw),
    [dividendByTicker],
  );

  const monthlyEstimateByMonth = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => {
        const m = i + 1;
        return dividendByTicker.reduce((sum, d) => {
          if (d.dividend_months.length === 0) return sum + d.estimated_monthly_krw;
          if (d.dividend_months.includes(m))
            return sum + Math.round(d.estimated_annual_krw / d.dividend_months.length);
          return sum;
        }, 0);
      }),
    [dividendByTicker],
  );

  const monthCells = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => {
        const m = i + 1;
        const monthStr = `${currentYear}-${String(m).padStart(2, "0")}`;
        const actual = divSummary?.monthly_breakdown.find((x) => x.month === monthStr);
        return {
          month: m,
          actual: actual?.amount ?? null,
          estimated: monthlyEstimateByMonth[i],
          isPast: m < currentMonth,
        };
      }),
    [currentYear, currentMonth, divSummary, monthlyEstimateByMonth],
  );

  const barData = useMemo(
    () =>
      monthCells.map((cell) => ({
        name: MONTH_LABELS[cell.month - 1],
        month: cell.month,
        isPast: cell.isPast,
        actual: cell.actual && cell.actual > 0 ? cell.actual : 0,
        estimated: !cell.actual || cell.actual === 0 ? cell.estimated : 0,
      })),
    [monthCells],
  );

  const selectedMonthTickers = useMemo(
    () => dividendByTicker.filter((d) => d.dividend_months.includes(selectedMonth)),
    [dividendByTicker, selectedMonth],
  );
  const monthStr = `${currentYear}-${String(selectedMonth).padStart(2, "0")}`;
  const selectedMonthActual = divSummary?.monthly_breakdown.find((x) => x.month === monthStr);
  const monthTickerActualMap: Record<string, number> = {};
  for (const entry of divSummary?.monthly_ticker_breakdown ?? []) {
    const key = `${entry.month}-${entry.ticker ?? ""}`;
    monthTickerActualMap[key] = (monthTickerActualMap[key] ?? 0) + entry.amount;
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700">
        <div className="grid grid-cols-3 divide-x divide-gray-100 dark:divide-gray-800">
          <div className="px-2 py-3 sm:px-4 sm:py-4">
            <p className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 whitespace-nowrap overflow-hidden">
              예상 연간 배당금
            </p>
            <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-green-600 whitespace-nowrap overflow-hidden">
              {totalEstimated > 0 ? `${fmtKrwShort(totalEstimated)}원` : "—"}
            </p>
            {totalEstimated > 0 && overallDividendYield != null ? (
              <p className="text-xs font-semibold text-green-500 mt-0.5 leading-tight">
                {overallDividendYield.toFixed(2)}% 배당수익률
              </p>
            ) : (
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                배당수익률 기준 추정
              </p>
            )}
          </div>
          <div className="px-2 py-3 sm:px-4 sm:py-4">
            <p className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 whitespace-nowrap overflow-hidden">
              올해 수령 배당금
            </p>
            <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-gray-900 dark:text-gray-50 whitespace-nowrap overflow-hidden">
              {received > 0 ? `${fmtKrwShort(received)}원` : "—"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {received > 0 ? "실제 수령 합계" : "배당 내역을 입력해주세요"}
            </p>
          </div>
          <div className="px-2 py-3 sm:px-4 sm:py-4">
            <p className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 whitespace-nowrap overflow-hidden">
              월평균 예상 배당금
            </p>
            <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-blue-600 whitespace-nowrap overflow-hidden">
              {estimatedMonthly > 0 ? `${fmtKrwShort(estimatedMonthly)}원` : "—"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">연간 예상 배당금 ÷ 12</p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 w-fit">
          {DIV_SUBTABS.map((t) => (
            <button
              key={t}
              onClick={() => setDivSubTab(t)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                divSubTab === t
                  ? "bg-white dark:bg-gray-700 shadow text-gray-900 dark:text-gray-50"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <Link
          to="/invest-plan?tab=배당 계획"
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          배당 목표 달성 현황 보기
        </Link>
      </div>

      {divSubTab === "종목별 배당" && dividendChartData.length > 0 && (
        <div className="space-y-4">
          <Suspense fallback={<SkeletonCard rows={3} />}>
            <TreemapChart data={dividendChartData} title="종목별 배당 비중 (예상 연간 기준)" />
          </Suspense>
          <div className="card-overflow">
            <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
              <h3 className="font-semibold text-gray-800 dark:text-gray-200">종목별 배당 내역</h3>
            </div>
            {/* 모바일 카드 뷰 */}
            <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
              {sortedByTicker.map((d) => {
                const pct =
                  totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0;
                const rowKey = `${d.ticker}-${d.market}`;
                const posDiv = positionsDivMap[rowKey] ?? tickerOnlyDivMap[d.ticker ?? ""];
                const investmentYield =
                  (posDiv?.investment_yield ?? 0) > 0
                    ? posDiv.investment_yield
                    : (d.investment_yield ?? 0);
                const barColor = weightBarColor(pct);
                const freqInfo = dividendFreqInfo(d.dividend_months, d.dividend_months_is_manual);
                return (
                  <div key={rowKey} className="px-4 py-3">
                    {/* Row 1: 종목명 + 연간 배당액 */}
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-sm text-gray-900 dark:text-gray-50 truncate">
                        {d.name}
                      </p>
                      <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 shrink-0 whitespace-nowrap">
                        {fmtKrwShort(d.estimated_annual_krw)}원
                      </span>
                    </div>
                    {/* Row 2: 티커·마켓 + 배당율 배지 | 비중 바 + % */}
                    <div className="flex items-center justify-between mt-0.5 gap-2">
                      <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                        <span className="text-xs text-gray-400 dark:text-gray-500 truncate">
                          {d.ticker} · {d.market}
                        </span>
                        {investmentYield > 0 && (
                          <span
                            className={`text-xs px-1.5 py-0.5 rounded-full ${yieldBadgeClass(investmentYield)}`}
                          >
                            {investmentYield.toFixed(2)}%
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <div className="w-14 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                          <div
                            className={`${barColor} h-full rounded-full`}
                            style={{ width: `${Math.min(pct, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500 dark:text-gray-400 w-9 text-right">
                          {pct.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                    {/* Row 3: 빈도 배지 + 월 배지들 */}
                    <div className="flex items-center gap-1 flex-wrap">
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqInfo.cls}`}
                      >
                        {freqInfo.label}
                      </span>
                      {d.dividend_months.length > 0 &&
                        d.dividend_months.length < 12 &&
                        d.dividend_months.map((m) => (
                          <span
                            key={m}
                            className="text-xs px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-100"
                          >
                            {m}월
                          </span>
                        ))}
                    </div>
                  </div>
                );
              })}
            </div>
            {/* 데스크탑 테이블 */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                    <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                      종목
                    </th>
                    <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                      투자배당수익율
                    </th>
                    <th className="py-2 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                      연간 배당금
                    </th>
                    <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                      비중
                    </th>
                    <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">
                      배당 빈도
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {sortedByTicker.map((d) => {
                    const pct =
                      totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0;
                    const rowKey = `${d.ticker}-${d.market}`;
                    const posDiv = positionsDivMap[rowKey] ?? tickerOnlyDivMap[d.ticker ?? ""];
                    const investmentYield =
                      (posDiv?.investment_yield ?? 0) > 0
                        ? posDiv.investment_yield
                        : (d.investment_yield ?? 0);
                    const barColor = weightBarColor(pct);
                    const freqInfo = dividendFreqInfo(
                      d.dividend_months,
                      d.dividend_months_is_manual,
                    );
                    return (
                      <tr
                        key={rowKey}
                        className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                      >
                        <td className="py-2 px-5">
                          <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            {d.ticker} · {d.market}
                          </p>
                        </td>
                        <td className="py-2 px-3 text-right font-medium text-green-600 dark:text-green-400">
                          {investmentYield > 0 ? `${investmentYield.toFixed(2)}%` : "—"}
                        </td>
                        <td className="py-2 px-4 text-right font-semibold text-gray-900 dark:text-gray-50">
                          {fmtKrwShort(d.estimated_annual_krw)}원
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex items-center justify-end gap-1.5">
                            <div className="w-14 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                              <div
                                className={`${barColor} h-full rounded-full`}
                                style={{ width: `${Math.min(pct, 100)}%` }}
                              />
                            </div>
                            <span className="text-xs text-gray-500 dark:text-gray-400 w-9 text-right">
                              {pct.toFixed(1)}%
                            </span>
                          </div>
                        </td>
                        <td className="py-2 px-5 text-right">
                          <div className="flex items-center justify-end gap-1 flex-wrap">
                            <span
                              className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqInfo.cls}`}
                            >
                              {freqInfo.label}
                            </span>
                            {d.dividend_months.length > 0 &&
                              d.dividend_months.length < 12 &&
                              d.dividend_months.map((m) => (
                                <span
                                  key={m}
                                  className="text-xs px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-100"
                                >
                                  {m}월
                                </span>
                              ))}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-800 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-500 dark:text-gray-400">합계</span>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                {fmtKrwShort(totalEstimated)}원
              </span>
            </div>
          </div>
        </div>
      )}
      {divSubTab === "종목별 배당" && dividendChartData.length === 0 && (
        <EmptyState title="배당 데이터가 없습니다." compact />
      )}

      {divSubTab === "월별 배당" && (
        <div className="space-y-4">
          <Suspense fallback={<SkeletonCard rows={3} />}>
            <MonthlyDividendChart
              barData={barData}
              currentYear={currentYear}
              selectedMonth={selectedMonth}
              isDark={isDark}
              onMonthSelect={setSelectedMonth}
            />
          </Suspense>
          <MonthlyTickerDetail
            selectedMonth={selectedMonth}
            selectedMonthTickers={selectedMonthTickers}
            selectedMonthActual={selectedMonthActual}
            monthStr={monthStr}
            monthlyEstimate={monthlyEstimateByMonth[selectedMonth - 1]}
            monthTickerActualMap={monthTickerActualMap}
          />
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-4">
              월별 균등화 추천
            </h3>
            <MonthlyOptimizationCard />
          </div>
        </div>
      )}
    </div>
  );
}
