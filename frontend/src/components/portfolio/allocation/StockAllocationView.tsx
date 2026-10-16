import { fmtKrw } from "@/utils/format";
import type { AllocationItem } from "@/types";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import WeightBarRow, { ListingBadge } from "./WeightBarRow";

const ETC_TICKER = "ETC";
const TOP_N = 5;

interface Props {
  items: AllocationItem[];
  /** 있으면 "전체 비중순 보기" 버튼을 보여준다 — 전체 순위는 아래 보유 종목 목록이 담당 */
  onShowAll?: () => void;
}

/** 종목별 비중 — 집중도 요약 + 상위 5종목 막대 + "기타 N종목". 전체 목록은 보유 종목 목록과 겹쳐 생략. */
export default function StockAllocationView({ items, onShowAll }: Props) {
  if (items.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-gray-400 dark:text-gray-500">
        보유 종목이 없어요.
      </p>
    );
  }

  const ranked = items.filter((i) => i.ticker !== ETC_TICKER);
  const top = ranked[0];
  const shown = ranked.slice(0, TOP_N);
  const topNPct = shown.reduce((sum, i) => sum + i.pct, 0);

  // 6위 이하 + 백엔드 "기타"(11위 이하, 이름 형식 "기타 N종목" — portfolio_service._build_stock_allocation)를 한 행으로 합친다
  const backendEtc = items.find((i) => i.ticker === ETC_TICKER);
  const backendEtcCount = Number(backendEtc?.name.match(/\d+/)?.[0] ?? 0);
  const restRanked = ranked.slice(TOP_N);
  const restCount = restRanked.length + backendEtcCount;
  const restPct = restRanked.reduce((sum, i) => sum + i.pct, 0) + (backendEtc?.pct ?? 0);
  const restValue =
    restRanked.reduce((sum, i) => sum + (i.value_krw ?? 0), 0) + (backendEtc?.value_krw ?? 0);
  const hasRest = restPct > 0;

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
              상위 {shown.length}종목 합계
            </div>
            <div className="text-sm font-semibold text-gray-800 dark:text-gray-100 tabular-nums">
              {topNPct.toFixed(1)}%
            </div>
          </div>
        </div>
      )}
      <ul className="mt-2 divide-y divide-gray-100 dark:divide-gray-700">
        {shown.map((item, idx) => (
          <WeightBarRow
            key={`${item.ticker ?? item.name}-${item.market ?? idx}`}
            label={item.name}
            pct={item.pct}
            leading={
              <span className="shrink-0 w-5 text-xs text-gray-400 dark:text-gray-500 tabular-nums">
                {idx + 1}
              </span>
            }
            badges={item.market && <ListingBadge market={item.market} />}
            subLeft={item.ticker}
            subRight={fmtKrw(item.value_krw ?? 0)}
          />
        ))}
        {hasRest && (
          <WeightBarRow
            label={restCount > 0 ? `기타 ${restCount}종목` : "기타"}
            pct={restPct}
            barClassName="bg-gray-300 dark:bg-gray-600"
            subLeft="아래 보유 종목 목록에서 확인"
            subRight={fmtKrw(restValue)}
          />
        )}
      </ul>
      {onShowAll && (
        <button
          type="button"
          onClick={onShowAll}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} mt-2 w-full text-sm text-blue-600 dark:text-blue-400 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
        >
          보유 종목 전체 비중순 보기
        </button>
      )}
    </div>
  );
}
