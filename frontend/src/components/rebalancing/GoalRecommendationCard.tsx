import { Target } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchGoalRecommendation } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { usePendingRecommendationStore } from "@/stores/pendingRecommendationStore";

interface Props {
  portfolioId: string;
}

/** 목표 역산 추천(로드맵 A 3단계) — 추천 비중이 있을 때만 카드를 표시한다.
 * 자동 반영되지 않으며, "적용" 클릭 시 포트폴리오 편집기에 추천 비중만 채워넣는다(저장은 사용자가 직접). */
export default function GoalRecommendationCard({ portfolioId }: Props) {
  const setPending = usePendingRecommendationStore((s) => s.setPending);

  const { data } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendation(portfolioId),
    queryFn: () => fetchGoalRecommendation(portfolioId),
    staleTime: STALE_TIME.LONG,
  });

  if (!data || !data.is_configured || data.recommended_items.length === 0) return null;

  return (
    <div className="mt-3 rounded-xl border border-purple-200 dark:border-purple-800/50 bg-purple-50 dark:bg-purple-900/20 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <Target size={13} className="text-purple-500 shrink-0" />
        <span className="text-xs font-semibold text-purple-700 dark:text-purple-400">
          목표 달성 추천 비중
        </span>
      </div>

      <p className="text-xs text-gray-600 dark:text-gray-300">
        목표 달성에 필요한 연 수익률 {data.required_return_pct?.toFixed(1)}% — 아래 비중으로
        조정하면 기대수익률 {data.expected_return_pct?.toFixed(1)}%
        {data.expected_dividend_yield_pct != null &&
          ` (배당수익률 약 ${data.expected_dividend_yield_pct.toFixed(1)}%)`}
        를 기대할 수 있습니다.
      </p>

      <ul className="space-y-1">
        {data.recommended_items.map((item) => (
          <li
            key={`${item.ticker}-${item.market}`}
            className="flex items-center justify-between text-xs"
          >
            <span className="text-gray-700 dark:text-gray-300">
              {item.name} <span className="text-gray-400">({item.ticker})</span>
            </span>
            <span className="font-medium text-purple-600 dark:text-purple-400">
              {item.weight.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>

      <div className="flex items-center justify-between gap-2 pt-1">
        <p className="text-xs text-purple-500 dark:text-purple-500">
          큐레이션 ETF 포함 참고용 제안 — 자동 반영되지 않습니다.
        </p>
        <button
          onClick={() => setPending(portfolioId, data.recommended_items)}
          className="shrink-0 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 px-3 py-1.5 rounded-lg transition-colors"
        >
          편집기에 적용
        </button>
      </div>
    </div>
  );
}
