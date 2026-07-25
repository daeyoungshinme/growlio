import { CASH_EQUIVALENT_TICKER, type GoalRecommendationItem } from "@/api/rebalancing";

/** 전체/연령대/기간별 3개 탭이 공유하는 추천 비중 목록 렌더링 — 종목명(+티커)·배당수익률·비중.
 * 합성 현금성 자산 항목(`CASH_EQUIVALENT_TICKER`)은 실제 매매 가능한 티커가 아니므로 괄호 표기를 생략한다. */
export default function RecommendationWeightList({ items }: { items: GoalRecommendationItem[] }) {
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li
          key={`${item.ticker}-${item.market}`}
          className="flex items-center justify-between text-xs"
        >
          <span className="text-gray-700 dark:text-gray-300">
            {item.name}
            {item.ticker !== CASH_EQUIVALENT_TICKER && (
              <span className="text-gray-400 dark:text-gray-500"> ({item.ticker})</span>
            )}
            {item.dividend_yield_pct != null && (
              <span className="text-gray-400 dark:text-gray-500">
                {" "}
                · 배당 {item.dividend_yield_pct.toFixed(1)}%
              </span>
            )}
          </span>
          <span className="font-medium text-teal-600 dark:text-teal-400">
            {item.weight.toFixed(1)}%
          </span>
        </li>
      ))}
    </ul>
  );
}
