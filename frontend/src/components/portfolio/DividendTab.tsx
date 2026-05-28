import { useMemo, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useThemeStore } from "../../stores/themeStore";
import { fmtKrw, fmtKrwShort } from "../../utils/format";
import { chartTooltipStyle } from "../../utils/chart";
import StatCard from "../common/StatCard";
import TreemapChart from "./TreemapChart";
import type { DividendByTicker, DividendYield } from "../../types";

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
}

const DIV_SUBTABS = ["종목별 배당", "월별 배당"] as const;
type DivSubTab = (typeof DIV_SUBTABS)[number];

const MONTH_LABELS = [
  "1월", "2월", "3월", "4월", "5월", "6월",
  "7월", "8월", "9월", "10월", "11월", "12월",
];

export default function DividendTab({ dividendData, divLoading, divSummary, dividendByTicker }: Props) {
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

  const totalEstimated = useMemo(
    () => dividendByTicker.reduce((s, d) => s + d.estimated_annual_krw, 0),
    [dividendByTicker],
  );
  const estimatedMonthly = useMemo(
    () => dividendByTicker.reduce((s, d) => s + d.estimated_monthly_krw, 0),
    [dividendByTicker],
  );
  const received = divSummary?.annual_received ?? 0;

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

  const monthlyEstimateByMonth = useMemo(
    () =>
      Array.from({ length: 12 }, (_, i) => {
        const m = i + 1;
        return dividendByTicker.reduce((sum, d) => {
          if (d.dividend_months.length === 0) return sum + d.estimated_monthly_krw;
          if (d.dividend_months.includes(m)) return sum + Math.round(d.estimated_annual_krw / d.dividend_months.length);
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
        return { month: m, actual: actual?.amount ?? null, estimated: monthlyEstimateByMonth[i], isPast: m < currentMonth };
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
        estimated: (!cell.actual || cell.actual === 0) ? cell.estimated : 0,
      })),
    [monthCells],
  );

  const selectedMonthTickers = dividendByTicker.filter((d) => d.dividend_months.includes(selectedMonth));
  const monthStr = `${currentYear}-${String(selectedMonth).padStart(2, "0")}`;
  const selectedMonthActual = divSummary?.monthly_breakdown.find((x) => x.month === monthStr);
  const monthTickerActualMap: Record<string, number> = {};
  for (const entry of divSummary?.monthly_ticker_breakdown ?? []) {
    const key = `${entry.month}-${entry.ticker ?? ""}`;
    monthTickerActualMap[key] = (monthTickerActualMap[key] ?? 0) + entry.amount;
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <StatCard
          label="예상 연간 배당금"
          value={totalEstimated > 0 ? `${fmtKrwShort(totalEstimated)}원` : "—"}
          sub="보유 종목 배당수익률 기준 추정"
          color="green"
          size="sm"
        />
        <StatCard
          label="올해 수령 배당금"
          value={received > 0 ? `${fmtKrwShort(received)}원` : "—"}
          sub={received > 0 ? "실제 수령 합계" : "배당 내역을 입력해주세요"}
          color="gray"
          size="sm"
        />
        <StatCard
          label="월평균 예상 배당금"
          value={estimatedMonthly > 0 ? `${fmtKrwShort(estimatedMonthly)}원` : "—"}
          sub="연간 예상 배당금 ÷ 12"
          color="blue"
          size="sm"
        />
      </div>

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

      {divSubTab === "종목별 배당" && dividendChartData.length > 0 && (
        <div className="space-y-4">
          <TreemapChart data={dividendChartData} title="종목별 배당 비중 (예상 연간 기준)" />
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
              <h3 className="font-semibold text-gray-800 dark:text-gray-200">종목별 배당 내역</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                    <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
                    <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">투자배당율</th>
                    <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당월</th>
                    <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">연간 배당금</th>
                    <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">비중</th>
                  </tr>
                </thead>
                <tbody>
                  {dividendByTicker
                    .filter((d) => d.estimated_annual_krw > 0)
                    .sort((a, b) => b.estimated_annual_krw - a.estimated_annual_krw)
                    .map((d) => {
                      const pct = totalEstimated > 0 ? (d.estimated_annual_krw / totalEstimated) * 100 : 0;
                      const rowKey = `${d.ticker}-${d.market}`;
                      const posDiv = positionsDivMap[rowKey] ?? tickerOnlyDivMap[d.ticker ?? ""];
                      const investmentYield = (posDiv?.investment_yield ?? 0) > 0 ? posDiv.investment_yield : (d.investment_yield ?? 0);
                      return (
                        <tr key={rowKey} className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                          <td className="py-2 px-5">
                            <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                            <p className="text-xs text-gray-400 dark:text-gray-500">{d.ticker} · {d.market}</p>
                          </td>
                          <td className="py-2 px-3 text-right">
                            {divLoading ? (
                              <span className="text-gray-300 dark:text-gray-600 text-xs">...</span>
                            ) : investmentYield > 0 ? (
                              <span className="font-medium text-green-600 dark:text-green-400">{investmentYield.toFixed(2)}%</span>
                            ) : (
                              <span className="text-gray-300 dark:text-gray-600">—</span>
                            )}
                          </td>
                          <td className="py-2 px-3 text-right">
                            {d.dividend_months.length === 0 ? (
                              <span className="text-gray-300 dark:text-gray-600">—</span>
                            ) : d.dividend_months.length === 12 ? (
                              <span className="text-xs px-1.5 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950 text-emerald-600 dark:text-emerald-400 font-medium">
                                월배당
                              </span>
                            ) : (
                              <div className="flex flex-wrap gap-0.5 justify-end">
                                {d.dividend_months.map((m) => (
                                  <span
                                    key={m}
                                    className={`text-xs px-1.5 py-0.5 rounded-full ${
                                      d.dividend_months_is_manual
                                        ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                        : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                    }`}
                                  >
                                    {m}
                                  </span>
                                ))}
                              </div>
                            )}
                          </td>
                          <td className="py-2 px-3 text-right font-semibold text-gray-900 dark:text-gray-50">
                            {fmtKrwShort(d.estimated_annual_krw)}원
                          </td>
                          <td className="py-2 px-5 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <div className="w-16 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                                <div className="bg-green-500 h-full rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
                              </div>
                              <span className="text-xs text-gray-500 dark:text-gray-400 w-10 text-right">{pct.toFixed(1)}%</span>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 font-semibold text-sm">
                    <td className="py-2.5 px-5 text-gray-500 dark:text-gray-400">합계</td>
                    <td className="py-2.5 px-3" />
                    <td className="py-2.5 px-3" />
                    <td className="py-2.5 px-3 text-right text-gray-900 dark:text-gray-50">{fmtKrwShort(totalEstimated)}원</td>
                    <td className="py-2.5 px-5 text-right text-gray-500 dark:text-gray-400">100%</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}
      {divSubTab === "종목별 배당" && dividendChartData.length === 0 && (
        <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-10">배당 데이터가 없습니다.</p>
      )}

      {divSubTab === "월별 배당" && (
        <div className="space-y-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
            <h3 className="font-semibold text-gray-800 dark:text-gray-200 mb-4">월별 배당 현황 ({currentYear})</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={barData}
                margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                onClick={(e) => {
                  if (e?.activePayload?.[0]) {
                    const d = e.activePayload[0].payload as { month: number };
                    setSelectedMonth(d.month);
                  }
                }}
              >
                <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#9CA3AF" }} axisLine={false} tickLine={false} />
                <YAxis
                  tickFormatter={(v: number) =>
                    v >= 1e8 ? `${(v / 1e8).toFixed(1)}억` : v >= 1e4 ? `${Math.round(v / 1e4)}만` : `${v}`
                  }
                  tick={{ fontSize: 11, fill: "#9CA3AF" }}
                  axisLine={false}
                  tickLine={false}
                  width={48}
                />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    `${fmtKrwShort(value)}원`,
                    name === "actual" ? "실수령" : "예상",
                  ]}
                  cursor={{ fill: isDark ? "rgba(255,255,255,0.05)" : "rgba(0,0,0,0.04)" }}
                  {...chartTooltipStyle(isDark)}
                />
                <Bar dataKey="actual" stackId="a" radius={[0, 0, 0, 0]} cursor="pointer">
                  {barData.map((entry) => (
                    <Cell
                      key={entry.month}
                      fill={entry.month === selectedMonth ? "#15803D" : "#16A34A"}
                      opacity={entry.month === selectedMonth ? 1 : 0.75}
                    />
                  ))}
                </Bar>
                <Bar dataKey="estimated" stackId="a" radius={[4, 4, 0, 0]} cursor="pointer">
                  {barData.map((entry) => (
                    <Cell
                      key={entry.month}
                      fill={
                        entry.month === selectedMonth
                          ? (entry.isPast ? "#9CA3AF" : "#4ADE80")
                          : (entry.isPast ? "#D1D5DB" : "#86EFAC")
                      }
                      opacity={entry.month === selectedMonth ? 1 : 0.75}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <p className="text-xs text-gray-300 dark:text-gray-600 mt-2 text-right">
              진한 초록: 실수령 · 연한 초록: 예상(미래) · 회색: 예상(과거 미수령) | 막대 클릭 시 해당 월 상세 표시
            </p>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
              <h3 className="font-semibold text-gray-800 dark:text-gray-200">
                {MONTH_LABELS[selectedMonth - 1]} 배당 종목
                {selectedMonthActual && selectedMonthActual.amount > 0 ? (
                  <span className="ml-2 text-xs font-normal text-green-600 dark:text-green-400">
                    실수령 {fmtKrwShort(selectedMonthActual.amount)}원
                  </span>
                ) : monthlyEstimateByMonth[selectedMonth - 1] > 0 ? (
                  <span className="ml-2 text-xs font-normal text-gray-400 dark:text-gray-500">
                    예상 {fmtKrwShort(monthlyEstimateByMonth[selectedMonth - 1])}원
                  </span>
                ) : null}
              </h3>
              <span className="text-xs text-gray-400 dark:text-gray-500">{selectedMonthTickers.length}개 종목</span>
            </div>
            {selectedMonthTickers.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                      <th className="py-2 px-5 text-left text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">종목</th>
                      <th className="py-2 px-3 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">투자배당수익율</th>
                      <th className="py-2 px-4 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당금</th>
                      <th className="py-2 px-5 text-right text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">배당월 설정</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedMonthTickers
                      .sort((a, b) => {
                        const aCount = a.dividend_months.length > 0 ? a.dividend_months.length : 12;
                        const bCount = b.dividend_months.length > 0 ? b.dividend_months.length : 12;
                        return Math.round(b.estimated_annual_krw / bCount) - Math.round(a.estimated_annual_krw / aCount);
                      })
                      .map((d) => {
                        const payCount = d.dividend_months.length > 0 ? d.dividend_months.length : 12;
                        const payAmt = Math.round(d.estimated_annual_krw / payCount);
                        const usdPerPayment =
                          d.estimated_monthly_usd != null ? (d.estimated_monthly_usd * 12) / payCount : null;
                        const actualAmt = monthTickerActualMap[`${monthStr}-${d.ticker ?? ""}`];
                        return (
                          <tr
                            key={`${d.ticker}-${d.market}`}
                            className="border-t border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                          >
                            <td className="py-2 px-5">
                              <p className="font-medium text-gray-900 dark:text-gray-50">{d.name}</p>
                              <p className="text-xs text-gray-400 dark:text-gray-500">{d.ticker} · {d.market}</p>
                            </td>
                            <td className="py-2 px-3 text-right font-medium text-green-600 dark:text-green-400">
                              {d.investment_yield > 0 ? `${d.investment_yield.toFixed(2)}%` : "—"}
                            </td>
                            <td className="py-2 px-4 text-right">
                              {actualAmt && actualAmt > 0 ? (
                                <span className="font-medium text-green-600 dark:text-green-400">
                                  수령 {fmtKrw(actualAmt)}
                                </span>
                              ) : d.currency === "USD" && usdPerPayment != null && usdPerPayment > 0 ? (
                                <span className="text-gray-500 dark:text-gray-400">
                                  {fmtKrw(payAmt)}(${usdPerPayment.toFixed(2)})
                                </span>
                              ) : payAmt > 0 ? (
                                <span className="text-gray-500 dark:text-gray-400">예상 {fmtKrw(payAmt)}</span>
                              ) : (
                                <span className="text-gray-300 dark:text-gray-600">—</span>
                              )}
                            </td>
                            <td className="py-2 px-5 text-right">
                              <span
                                className={`text-xs px-2 py-0.5 rounded-full ${
                                  d.dividend_months_is_manual
                                    ? "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400"
                                    : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
                                }`}
                              >
                                {d.dividend_months_is_manual ? "수동" : "자동"}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-400 dark:text-gray-500 text-center py-8">이 달에 배당 예정 종목이 없습니다.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
