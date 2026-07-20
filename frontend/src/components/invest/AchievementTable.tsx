import { fmtKrw } from "@/utils/format";
import EmptyState from "@/components/common/EmptyState";

function pctColor(pct: number) {
  if (pct >= 100) return "text-red-500";
  if (pct >= 80) return "text-gray-700 dark:text-gray-300";
  return "text-blue-500";
}

export interface AchievementRow {
  key: string;
  label: string;
  projected: number;
  actual: number | null;
  achievementPct: number | null;
}

interface Props {
  title: string;
  subtitle: string;
  emptyTitle: string;
  projectedLabel: string;
  actualLabel: string;
  rows: AchievementRow[];
  flat?: boolean;
  /** true면 모바일 카드 목록도 데스크탑처럼 내부 스크롤(최대 360px)로 제한 */
  scrollable?: boolean;
}

export default function AchievementTable({
  title,
  subtitle,
  emptyTitle,
  projectedLabel,
  actualLabel,
  rows,
  flat,
  scrollable,
}: Props) {
  if (rows.length === 0) {
    return (
      <div className={flat ? undefined : "card"}>
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-3">{title}</h3>
        <EmptyState title={emptyTitle} compact />
      </div>
    );
  }

  const reversed = [...rows].reverse();

  return (
    <div className={flat ? undefined : "card"}>
      <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-1">{title}</h3>
      <p className="text-xs text-gray-400 dark:text-gray-500">{subtitle}</p>
      <p className="text-xs text-gray-400 dark:text-gray-500 mb-3">
        현재 설정된 목표 기준으로 계산되며, 목표를 변경하면 과거 수치도 새 기준으로 다시 계산됩니다.
      </p>
      {/* 모바일 카드 뷰 */}
      <div
        className={`sm:hidden divide-y divide-gray-100 dark:divide-gray-700 ${
          scrollable ? "max-h-[360px] overflow-y-auto overscroll-contain" : ""
        }`}
      >
        {reversed.map((row) => {
          const diff = row.actual !== null ? row.actual - row.projected : null;
          return (
            <div key={row.key} className="py-2.5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                  {row.label}
                </p>
                <span
                  className={`text-sm font-bold ${row.achievementPct !== null ? pctColor(row.achievementPct) : "text-gray-400 dark:text-gray-500"}`}
                >
                  {row.achievementPct !== null ? `${row.achievementPct.toFixed(1)}%` : "—"}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-gray-400 dark:text-gray-500 flex-wrap">
                <span>
                  {projectedLabel} {fmtKrw(row.projected)}
                </span>
                <span>
                  {actualLabel} {row.actual !== null ? fmtKrw(row.actual) : "—"}
                </span>
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
      <div
        className={`hidden sm:block overflow-x-auto ${scrollable ? "max-h-[440px] overflow-y-auto" : ""}`}
      >
        <table className="w-full text-sm">
          <thead className={scrollable ? "sticky top-0 bg-white dark:bg-gray-900" : undefined}>
            <tr className="text-xs text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-700">
              <th className="text-left py-2 pr-3 font-medium">기간</th>
              <th className="text-right py-2 px-3 font-medium">{projectedLabel}</th>
              <th className="text-right py-2 px-3 font-medium">{actualLabel}</th>
              <th className="text-right py-2 px-3 font-medium">계획 대비 달성율</th>
              <th className="text-right py-2 pl-3 font-medium">차이</th>
            </tr>
          </thead>
          <tbody>
            {reversed.map((row) => {
              const diff = row.actual !== null ? row.actual - row.projected : null;
              return (
                <tr
                  key={row.key}
                  className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800"
                >
                  <td className="py-2.5 pr-3 font-medium text-gray-800 dark:text-gray-200">
                    {row.label}
                  </td>
                  <td className="py-2.5 px-3 text-right text-gray-600 dark:text-gray-400">
                    {fmtKrw(row.projected)}
                  </td>
                  <td className="py-2.5 px-3 text-right text-gray-900 dark:text-gray-50 font-semibold">
                    {row.actual !== null ? fmtKrw(row.actual) : "—"}
                  </td>
                  <td
                    className={`py-2.5 px-3 text-right font-bold ${
                      row.achievementPct !== null
                        ? pctColor(row.achievementPct)
                        : "text-gray-400 dark:text-gray-500"
                    }`}
                  >
                    {row.achievementPct !== null ? `${row.achievementPct.toFixed(1)}%` : "—"}
                  </td>
                  <td
                    className={`py-2.5 pl-3 text-right text-xs ${
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
