import { useState, useMemo } from "react";
import { ChevronDown } from "lucide-react";
import { fmtKrw, fmtMonth } from "../../utils/format";
import { pnlColor } from "../../utils/colors";
import MonthlyTrendChart from "../trend/MonthlyTrendChart";
import type { MonthlyTrend } from "../../api/dashboard";

interface Props {
  monthlyTrend: MonthlyTrend[];
}

export default function MonthlyTrendSection({ monthlyTrend }: Props) {
  const [showDetail, setShowDetail] = useState(false);

  const reversedTrend = useMemo(
    () => [...(monthlyTrend ?? [])].reverse(),
    [monthlyTrend]
  );

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">월별 자산 추이 (최근 12개월)</h2>
      <MonthlyTrendChart data={monthlyTrend ?? []} />
      <button
        onClick={() => setShowDetail((v) => !v)}
        className="mt-4 w-full flex items-center justify-between py-2 px-3 text-xs text-gray-400 dark:text-gray-500 font-medium hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors"
      >
        <span>월별 상세</span>
        <ChevronDown className={`w-4 h-4 transition-transform duration-200 ${showDetail ? "rotate-180" : ""}`} />
      </button>
      {showDetail && (
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
              {reversedTrend.length === 0 ? (
                <tr><td colSpan={3} className="py-8 text-center text-gray-300 dark:text-gray-600 text-xs">데이터 없음</td></tr>
              ) : (
                reversedTrend.map((row, i, arr) => {
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
  );
}
