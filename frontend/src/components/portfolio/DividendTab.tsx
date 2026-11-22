import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useThemeStore } from "@/stores/themeStore";
import { fmtKrw } from "@/utils/format";
import SkeletonCard from "@/components/common/SkeletonCard";
import PageLoadError from "@/components/common/PageLoadError";
import SegmentedControl from "@/components/common/SegmentedControl";

const TreemapChart = lazy(() => import("./TreemapChart"));
const MonthlyDividendChart = lazy(() => import("./MonthlyDividendChart"));
const YearlyDividendChart = lazy(() => import("./YearlyDividendChart"));
import MonthlyTickerDetail from "./MonthlyTickerDetail";
import type { DividendByTicker, DividendYield } from "@/types";
import {
  MONTH_LABELS,
  dividendFreqInfo,
  weightBarColor,
  yieldBadgeClass,
} from "@/utils/dividendUtils";
import EmptyState from "@/components/common/EmptyState";
import { TOUCH_HEIGHT_MIN, TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { marketLabel } from "@/constants/markets";
import type { DividendSummary } from "@/api/dividends";
import { investPlanUrl } from "@/utils/tabUrl";

interface Props {
  dividendData: DividendYield[];
  /** 부모(PortfolioPage)가 보유 종목 표용으로 만든 `${ticker}-${market}` 맵 — 같은 맵을 다시 만들지 않는다 */
  dividendMap: Record<string, DividendYield>;
  divLoading: boolean;
  /** 배당 조회 실패 — 없으면 실패가 "배당 데이터가 없습니다"로 보였다(plans/144 B1) */
  divError?: boolean;
  onRetry?: () => void;
  divSummary: DividendSummary | undefined;
  dividendByTicker: DividendByTicker[];
  totalInvestedKrw?: number;
}

const DIV_SUBTABS = ["종목별 배당", "월별 배당"] as const;
type DivSubTab = (typeof DIV_SUBTABS)[number];

function WeightBar({ pct, className }: { pct: number; className: string }) {
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <div className="w-14 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
        <div
          className={`${weightBarColor(pct)} h-full rounded-full`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 dark:text-gray-400 w-9 text-right">
        {pct.toFixed(1)}%
      </span>
    </div>
  );
}

function FreqBadges({ months, className = "" }: { months: number[]; className?: string }) {
  const freqInfo = dividendFreqInfo(months);
  return (
    <div className={`flex items-center gap-1 flex-wrap ${className}`}>
      <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${freqInfo.cls}`}>
        {freqInfo.label}
      </span>
      {months.length > 0 &&
        months.length < 12 &&
        months.map((m) => (
          <span
            key={m}
            className="text-xs px-1.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-600 text-slate-600 dark:text-slate-100"
          >
            {m}월
          </span>
        ))}
    </div>
  );
}

export default function DividendTab({
  dividendData,
  dividendMap: positionsDivMap,
  divLoading,
  divError = false,
  onRetry,
  divSummary,
  dividendByTicker,
  totalInvestedKrw,
}: Props) {
  const isDark = useThemeStore((s) => s.isDark);
  const [searchParams, setSearchParams] = useSearchParams();
  const rawDivSubTab = searchParams.get("divTab");
  const divSubTab: DivSubTab = (DIV_SUBTABS as readonly string[]).includes(rawDivSubTab ?? "")
    ? (rawDivSubTab as DivSubTab)
    : "종목별 배당";
  const setDivSubTab = useCallback(
    (next: DivSubTab) => {
      setSearchParams(
        (prev) => {
          prev.set("divTab", next);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  const [selectedMonth, setSelectedMonth] = useState<number>(new Date().getMonth() + 1);

  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1;

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

  const tickerRows = useMemo(
    () =>
      sortedByTicker.map((d) => {
        const rowKey = `${d.ticker}-${d.market}`;
        const posDiv = positionsDivMap[rowKey] ?? tickerOnlyDivMap[d.ticker ?? ""];
        const posYield = posDiv?.investment_yield ?? 0;
        return {
          d,
          rowKey,
          pct: totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0,
          investmentYield: posYield > 0 ? posYield : (d.investment_yield ?? 0),
        };
      }),
    [sortedByTicker, positionsDivMap, tickerOnlyDivMap, totalEstimated],
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
          estimated: monthlyEstimateByMonth[i] ?? 0,
          isPast: m < currentMonth,
        };
      }),
    [currentYear, currentMonth, divSummary, monthlyEstimateByMonth],
  );

  const barData = useMemo(
    () =>
      monthCells.map((cell) => ({
        name: MONTH_LABELS[cell.month - 1] ?? `${cell.month}월`,
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

  if (divLoading) {
    return <SkeletonCard rows={4} />;
  }
  const retry = onRetry ?? (() => {});
  // 아무것도 못 받았으면 빈 상태 대신 실패 화면 — 일부만 실패했으면 아래 배너로 알린다
  if (divError && dividendByTicker.length === 0 && !divSummary) {
    return <PageLoadError message="배당 정보를 불러오지 못했습니다" onRetry={retry} />;
  }

  return (
    <div className="space-y-6">
      {divError && (
        <div
          role="alert"
          className="flex items-center justify-between gap-2 rounded-xl border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 px-3 py-2"
        >
          <p className="text-xs text-red-700 dark:text-red-400">
            일부 배당 정보를 불러오지 못해 합계가 실제보다 적을 수 있어요
          </p>
          <button
            type="button"
            onClick={retry}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 px-2 text-xs text-red-600 dark:text-red-400 hover:underline`}
          >
            다시 시도
          </button>
        </div>
      )}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700">
        <div className="grid grid-cols-3 divide-x divide-gray-100 dark:divide-gray-800">
          <div className="px-2 py-3 sm:px-4 sm:py-4">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 leading-tight break-keep">
              예상 연간 배당금
            </p>
            <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-green-600 break-keep">
              {totalEstimated > 0 ? fmtKrw(totalEstimated) : "—"}
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
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 leading-tight break-keep">
              올해 수령 배당금
            </p>
            <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-gray-900 dark:text-gray-50 break-keep">
              {received > 0 ? fmtKrw(received) : "—"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {received > 0 ? "실제 수령 합계" : "배당 내역을 입력해주세요"}
            </p>
          </div>
          <div className="px-2 py-3 sm:px-4 sm:py-4">
            <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 leading-tight break-keep">
              월평균 예상 배당금
            </p>
            <p className="text-base sm:text-lg font-bold mt-1 leading-tight text-blue-600 break-keep">
              {estimatedMonthly > 0 ? fmtKrw(estimatedMonthly) : "—"}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">연간 예상 배당금 ÷ 12</p>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        {/* 자산 › 투자현황 › 배당 아래 3단 — pill 대신 segmented (docs/plans/67) */}
        <SegmentedControl
          ariaLabel="배당 보기"
          options={DIV_SUBTABS.map((v) => ({ value: v, label: v }))}
          value={divSubTab}
          onChange={setDivSubTab}
        />
        {/* 월별 보기는 아래에 균등화 추천 링크가 있어 같은 목적지 링크를 한 화면에 두 번 두지 않는다 */}
        {divSubTab === "종목별 배당" && (
          <Link
            to={investPlanUrl("배당 계획")}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
          >
            배당 목표 달성 현황 보기
          </Link>
        )}
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
              {tickerRows.map(({ d, pct, rowKey, investmentYield }) => {
                return (
                  <div key={rowKey} className="px-4 py-3">
                    {/* Row 1: 종목명 + 연간 배당액 */}
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-sm text-gray-900 dark:text-gray-50 truncate">
                        {d.name}
                      </p>
                      <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 shrink-0 whitespace-nowrap">
                        {fmtKrw(d.estimated_annual_krw)}
                      </span>
                    </div>
                    {/* Row 2: 티커·마켓 + 배당율 배지 | 비중 바 + % */}
                    <div className="flex items-center justify-between mt-0.5 gap-2">
                      <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                        <span className="text-xs text-gray-400 dark:text-gray-500 truncate">
                          {d.ticker} · {marketLabel(d.market)}
                        </span>
                        {investmentYield > 0 && (
                          <span
                            className={`text-xs px-1.5 py-0.5 rounded-full ${yieldBadgeClass(investmentYield)}`}
                          >
                            {investmentYield.toFixed(2)}%
                          </span>
                        )}
                      </div>
                      <WeightBar pct={pct} className="shrink-0" />
                    </div>
                    {/* Row 3: 빈도 배지 + 월 배지들 */}
                    <FreqBadges months={d.dividend_months} />
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
                  {tickerRows.map(({ d, pct, rowKey, investmentYield }) => {
                    return (
                      <tr
                        key={rowKey}
                        className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                      >
                        <td className="py-2 px-5">
                          <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                          <p className="text-xs text-gray-400 dark:text-gray-500">
                            {d.ticker} · {marketLabel(d.market)}
                          </p>
                        </td>
                        <td className="py-2 px-3 text-right font-medium text-green-600 dark:text-green-400">
                          {investmentYield > 0 ? `${investmentYield.toFixed(2)}%` : "—"}
                        </td>
                        <td className="py-2 px-4 text-right font-semibold text-gray-900 dark:text-gray-50">
                          {fmtKrw(d.estimated_annual_krw)}
                        </td>
                        <td className="py-2 px-3">
                          <WeightBar pct={pct} className="justify-end" />
                        </td>
                        <td className="py-2 px-5 text-right">
                          <FreqBadges months={d.dividend_months} className="justify-end" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
      {divSubTab === "종목별 배당" && dividendChartData.length === 0 && !divError && (
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
            monthlyEstimate={monthlyEstimateByMonth[selectedMonth - 1] ?? 0}
            monthTickerActualMap={monthTickerActualMap}
          />
          <Suspense fallback={<SkeletonCard rows={3} />}>
            <YearlyDividendChart />
          </Suspense>
          <Link
            to={investPlanUrl("배당 계획")}
            className={`flex items-center ${TOUCH_HEIGHT_MIN} text-sm text-blue-600 dark:text-blue-400 hover:underline`}
          >
            배당이 적은 달을 채우려면 계획 › 배당 계획의 월별 균등화 추천을 확인하세요 →
          </Link>
        </div>
      )}
    </div>
  );
}
