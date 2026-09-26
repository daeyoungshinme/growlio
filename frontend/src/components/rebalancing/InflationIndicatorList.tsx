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

/** 미국 물가 지표(전년比 + 다음 발표일) 목록. 진단탭에서 별도 카드였으나 같은 매크로 정보라
 * `MarketSignalBanner` 상세 영역 안으로 병합됐다(계획 37 U9). */
export default function InflationIndicatorList({ data }: Props) {
  if (data.length === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-gray-600 dark:text-gray-300">물가 지표 (미국)</p>
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
  );
}
