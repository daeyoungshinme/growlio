import { fmtKrw } from "@/utils/format";
import type { AllocationItem } from "@/types";
import WeightBarRow, { ListingBadge } from "./WeightBarRow";

const ETC_TICKER = "ETC";
const TOP_N_SUMMARY = 5;

interface Props {
  items: AllocationItem[];
}

/** 종목별 비중 — 상위 10종목 순위 막대 + "기타 N종목", 상단에 집중도 요약. */
export default function StockAllocationView({ items }: Props) {
  if (items.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
        보유 종목이 없어요.
      </p>
    );
  }

  const ranked = items.filter((i) => i.ticker !== ETC_TICKER);
  const top = ranked[0];
  const topNPct = ranked.slice(0, TOP_N_SUMMARY).reduce((sum, i) => sum + i.pct, 0);

  return (
    <div>
      {top && (
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2 min-w-0">
            <div className="text-xs text-gray-500 dark:text-gray-400">최대 종목</div>
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
              {top.name} <span className="tabular-nums">{top.pct.toFixed(1)}%</span>
            </div>
          </div>
          <div className="rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2">
            <div className="text-xs text-gray-500 dark:text-gray-400">
              상위 {Math.min(TOP_N_SUMMARY, ranked.length)}종목 합계
            </div>
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 tabular-nums">
              {topNPct.toFixed(1)}%
            </div>
          </div>
        </div>
      )}
      <ul className="mt-2 divide-y divide-gray-100 dark:divide-gray-700">
        {items.map((item, idx) => {
          const isEtc = item.ticker === ETC_TICKER;
          return (
            <WeightBarRow
              key={`${item.ticker ?? item.name}-${item.market ?? idx}`}
              label={item.name}
              pct={item.pct}
              leading={
                !isEtc && (
                  <span className="shrink-0 w-5 text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                    {idx + 1}
                  </span>
                )
              }
              badges={!isEtc && item.market && <ListingBadge market={item.market} />}
              barClassName={isEtc ? "bg-gray-300 dark:bg-gray-600" : undefined}
              subLeft={isEtc ? "아래 보유 종목 표에서 확인" : item.ticker}
              subRight={fmtKrw(item.value_krw ?? 0)}
            />
          );
        })}
      </ul>
    </div>
  );
}
