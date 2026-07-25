import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { SuggestedGoalCandidate } from "@/api/rebalancing";
import { type GoalCandidateTicker, updateGoalCandidateTickers } from "@/api/settings";
import { invalidateGoalRecommendationData } from "@/utils/queryInvalidation";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

/** 제안된 배당 후보(`suggested_candidates`)를 현재 등록된 후보 목록에 병합해 저장한다 —
 * 승인 전에는 비중 계산에 반영되지 않으므로 사용자가 "후보에 추가" 버튼을 눌러야만 호출된다.
 * `RecommendationCard.tsx`(리밸런싱 탭)와 `DividendPlanSection.tsx`(배당 계획 탭)가 공용한다. */
export function useAddSuggestedCandidates(currentCandidates: GoalCandidateTicker[]) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (suggested: SuggestedGoalCandidate[]) => {
      const merged = [...currentCandidates];
      for (const s of suggested) {
        if (!merged.some((c) => c.ticker === s.ticker && c.market === s.market)) {
          merged.push({
            ticker: s.ticker,
            name: s.name,
            market: s.market,
            asset_class: s.asset_class,
          });
        }
      }
      return updateGoalCandidateTickers(merged);
    },
    onSuccess: async () => {
      toast("후보 ETF 목록에 추가되었습니다 — 다음 추천부터 비중 계산에 반영돼요", "success");
      await invalidateGoalRecommendationData(queryClient);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });
}
