import { TrendingDown, TrendingUp } from "lucide-react";
import type { InflationIndicatorSummary } from "@/api/economicIndicators";
import { fmtPct } from "@/utils/format";

interface Props {
  data: InflationIndicatorSummary[];
}

function formatReleaseDate(dateStr: string | null): string {
  if (!dateStr) return "발표일 미정";
  const [, month, day] = dateStr.split("-").map(Number);
  return `${month}월 ${day}일 발표 예정`;
}

export default function InflationSummaryCard({ data }: Props) {
  if (data.length === 0) return null;

  return (
    <div className="rounded-xl border bg-white border-gray-200 dark:bg-gray-800 dark:border-gray-700">
      <div className="px-4 py-3">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
          물가 지표 (미국)
        </span>
      </div>
      <div className="px-4 pb-3 space-y-2.5 border-t border-inherit pt-2.5">
        {data.map((item) => {
          const yoy = item.yoy_change_pct;
          const TrendIcon = yoy != null && yoy < 0 ? TrendingDown : TrendingUp;
          return (
            <div key={item.code} className="flex items-center gap-2">
              <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">
                {item.name}
              </span>
              {yoy != null && (
                <TrendIcon size={12} className="text-gray-400 dark:text-gray-500 shrink-0" />
              )}
              <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                {fmtPct(yoy, 1)} (전년比)
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
                {formatReleaseDate(item.next_release_date)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
