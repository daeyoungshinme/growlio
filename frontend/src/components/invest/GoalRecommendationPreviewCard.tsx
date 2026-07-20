import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { fetchOverallGoalRecommendation } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { fmtPct } from "@/utils/format";

export default function GoalRecommendationPreviewCard() {
  const { data, isLoading } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    staleTime: STALE_TIME.LONG,
  });

  if (isLoading || !data) return null;

  return (
    <div className="card">
      <div className="flex items-center gap-2 mb-2">
        <TrendingUp size={16} className="text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          목표 기반 포트폴리오 추천
        </h3>
      </div>
      {!data.is_configured ? (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          투자 목표를 설정하면 추천 비중을 볼 수 있어요.
        </p>
      ) : (
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 mb-2">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">목표 달성 필요 수익률</p>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">
              {fmtPct(data.required_return_pct)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">추천 포트폴리오 기대수익률</p>
            <p className="text-sm font-semibold text-indigo-600 dark:text-indigo-400 mt-0.5">
              {fmtPct(data.expected_return_pct)}
            </p>
          </div>
          <div className="col-span-2 text-xs text-gray-400 dark:text-gray-500">
            추천 종목 {data.recommended_items.length}개
          </div>
        </div>
      )}
      <Link
        to="/rebalancing?rtab=포트폴리오"
        className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
      >
        자세히 보기 →
      </Link>
    </div>
  );
}
