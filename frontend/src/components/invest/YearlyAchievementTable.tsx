import type { YearlyAchievement } from "../../api/invest";
import { fmtKrw } from "../../utils/format";

function pctColor(pct: number) {
  if (pct >= 100) return "text-red-500";
  if (pct >= 80) return "text-gray-700 dark:text-gray-300";
  return "text-blue-500";
}

interface Props {
  data: YearlyAchievement[];
}

export default function YearlyAchievementTable({ data }: Props) {
  const past = data.filter((d) => d.has_data);

  if (past.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-3">연별 달성율</h3>
        <p className="text-sm text-gray-400 dark:text-gray-500">스냅샷 데이터가 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-3">연별 달성율</h3>
      {/* 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {[...past].reverse().map((row) => {
          const diff = row.actual_year_end_krw !== null ? row.actual_year_end_krw - row.projected_year_end_krw : null;
          return (
            <div key={row.year} className="py-2.5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">{row.year}년</p>
                <span className={`text-sm font-bold ${row.achievement_pct !== null ? pctColor(row.achievement_pct) : "text-gray-400 dark:text-gray-500"}`}>
                  {row.achievement_pct !== null ? `${row.achievement_pct.toFixed(1)}%` : "—"}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 dark:text-gray-500 flex-wrap">
                <span>이론 {fmtKrw(row.projected_year_end_krw)}</span>
                <span>실제 {row.actual_year_end_krw !== null ? fmtKrw(row.actual_year_end_krw) : "—"}</span>
                {diff !== null && (
                  <span className={diff >= 0 ? "text-red-500" : "text-blue-500"}>
                    {diff >= 0 ? "+" : ""}{fmtKrw(diff)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">
              <th className="text-left py-2 font-medium">연도</th>
              <th className="text-right py-2 font-medium">이론 연말값</th>
              <th className="text-right py-2 font-medium">실제 연말값</th>
              <th className="text-right py-2 font-medium">달성율</th>
              <th className="text-right py-2 font-medium">차이</th>
            </tr>
          </thead>
          <tbody>
            {[...past].reverse().map((row) => {
              const diff =
                row.actual_year_end_krw !== null
                  ? row.actual_year_end_krw - row.projected_year_end_krw
                  : null;
              return (
                <tr key={row.year} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                  <td className="py-2.5 font-medium text-gray-800 dark:text-gray-200">{row.year}년</td>
                  <td className="py-2.5 text-right text-gray-600 dark:text-gray-400">
                    {fmtKrw(row.projected_year_end_krw)}
                  </td>
                  <td className="py-2.5 text-right text-gray-900 dark:text-gray-50 font-semibold">
                    {row.actual_year_end_krw !== null ? fmtKrw(row.actual_year_end_krw) : "—"}
                  </td>
                  <td
                    className={`py-2.5 text-right font-bold ${
                      row.achievement_pct !== null
                        ? pctColor(row.achievement_pct)
                        : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    {row.achievement_pct !== null
                      ? `${row.achievement_pct.toFixed(1)}%`
                      : "—"}
                  </td>
                  <td
                    className={`py-2.5 text-right text-xs ${
                      diff === null
                        ? "text-gray-400 dark:text-gray-500"
                        : diff >= 0
                        ? "text-red-500"
                        : "text-blue-500"
                    }`}
                  >
                    {diff !== null ? `${diff >= 0 ? "+" : ""}${fmtKrw(diff)}` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
