import type { DCAProjectionPoint } from "@/api/invest";
import { fmtKrw } from "@/utils/format";
import EmptyState from "@/components/common/EmptyState";

function pctColor(pct: number) {
  if (pct >= 100) return "text-red-500";
  if (pct >= 80) return "text-gray-700 dark:text-gray-300";
  return "text-blue-500";
}

interface Props {
  data: DCAProjectionPoint[];
  flat?: boolean;
}

export default function MonthlyAchievementTable({ data, flat }: Props) {
  const today = new Date().toISOString().slice(0, 7);
  const past = data.filter((d) => d.month <= today && d.has_data).slice(-24);

  if (past.length === 0) {
    return (
      <div className={flat ? undefined : "card"}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-3">
          월별 계획 대비 달성율
        </h3>
        <EmptyState title="스냅샷 데이터가 없습니다." compact />
      </div>
    );
  }

  return (
    <div className={flat ? undefined : "card"}>
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">
        월별 계획 대비 달성율 (최근 24개월)
      </h3>
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
        이론값(복리 계획 곡선) 대비 실제 자산 비율입니다
      </p>
      {/* 모바일 카드 뷰 */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {[...past].reverse().map((row) => {
          const diff = row.actual_krw !== null ? row.actual_krw - row.projected_krw : null;
          return (
            <div key={row.month} className="py-2.5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{row.month}</p>
                <span
                  className={`text-sm font-semibold ${row.achievement_pct !== null ? pctColor(row.achievement_pct) : "text-gray-400 dark:text-gray-500"}`}
                >
                  {row.achievement_pct !== null ? `${row.achievement_pct.toFixed(1)}%` : "—"}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 dark:text-gray-500 flex-wrap">
                <span>이론 {fmtKrw(row.projected_krw)}</span>
                <span>실제 {row.actual_krw !== null ? fmtKrw(row.actual_krw) : "—"}</span>
                {diff !== null && (
                  <span className={diff >= 0 ? "text-red-500" : "text-blue-500"}>
                    {diff >= 0 ? "+" : ""}
                    {fmtKrw(diff)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden sm:block overflow-x-auto max-h-[440px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white dark:bg-gray-900">
            <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">
              <th className="text-left py-2 pr-3 font-medium">월</th>
              <th className="text-right py-2 px-3 font-medium">이론값</th>
              <th className="text-right py-2 px-3 font-medium">실제값</th>
              <th className="text-right py-2 px-3 font-medium">계획 대비 달성율</th>
              <th className="text-right py-2 pl-3 font-medium">차이</th>
            </tr>
          </thead>
          <tbody>
            {[...past].reverse().map((row) => {
              const diff = row.actual_krw !== null ? row.actual_krw - row.projected_krw : null;
              return (
                <tr
                  key={row.month}
                  className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <td className="py-2 pr-3 text-gray-700 dark:text-gray-300">{row.month}</td>
                  <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                    {fmtKrw(row.projected_krw)}
                  </td>
                  <td className="py-2 px-3 text-right text-gray-900 dark:text-gray-50 font-medium">
                    {row.actual_krw !== null ? fmtKrw(row.actual_krw) : "—"}
                  </td>
                  <td
                    className={`py-2 px-3 text-right font-semibold ${
                      row.achievement_pct !== null
                        ? pctColor(row.achievement_pct)
                        : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    {row.achievement_pct !== null ? `${row.achievement_pct.toFixed(1)}%` : "—"}
                  </td>
                  <td
                    className={`py-2 pl-3 text-right text-xs ${
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
