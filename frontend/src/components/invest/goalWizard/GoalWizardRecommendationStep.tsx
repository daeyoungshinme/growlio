import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { createPortfolio } from "@/api/portfolios";
import { fetchOverallGoalRecommendation } from "@/api/rebalancing";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { fmtPct } from "@/utils/format";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData } from "@/utils/queryInvalidation";
import { normalizeWeights } from "@/utils/recommendationDrift";
import GoalWizardLoading from "./GoalWizardLoading";

/** 6단계 — 자동 저장이 끝난 뒤 전체 자산 기준 목표 역산 추천을 보여주고, 그 비중으로 새 포트폴리오를 만든다. */
export default function GoalWizardRecommendationStep({
  settingsPersisted,
  onClose,
}: {
  settingsPersisted: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: recommendation, isLoading: recommendationLoading } = useQuery({
    queryKey: QUERY_KEYS.goalRecommendationOverall,
    queryFn: fetchOverallGoalRecommendation,
    enabled: settingsPersisted,
    staleTime: 0,
  });

  const navigate = useNavigate();
  const createPortfolioMutation = useMutation({
    mutationFn: () =>
      createPortfolio({
        name: "추천 포트폴리오",
        // 반올림 합계가 100±0.01을 벗어나면 백엔드 검증에 걸리므로 추천 카드와 같은 정규화를 거친다
        items: normalizeWeights(recommendation?.recommended_items ?? []),
      }),
    // 생성만 하고 계획탭에 머물면 계좌 미연결 고아 포트폴리오로 남기 쉬움 — 바로 해당 포트폴리오로
    // 이동시켜 계좌 연결·드리프트 진단으로 이어지게 한다.
    onSuccess: async (created) => {
      toast("추천 포트폴리오가 생성되었습니다 — 계좌를 연결하면 비중 진단이 시작됩니다", "success");
      await invalidatePortfolioData(queryClient);
      onClose();
      void navigate(`/rebalancing?rtab=포트폴리오&portfolioId=${created.id}`);
    },
    onError: (e) => toast(extractErrorMessage(e), "error"),
  });

  return (
    <div className="space-y-3">
      {(!settingsPersisted || recommendationLoading) && (
        <GoalWizardLoading text="추천 포트폴리오를 계산하고 있어요..." />
      )}
      {settingsPersisted && recommendation && recommendation.recommended_items.length > 0 && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800">
              <p className="text-xs text-gray-500 dark:text-gray-400">기대수익률</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                {recommendation.expected_return_pct != null
                  ? fmtPct(recommendation.expected_return_pct)
                  : "—"}
              </p>
            </div>
            <div className="p-2.5 rounded-lg bg-gray-50 dark:bg-gray-800">
              <p className="text-xs text-gray-500 dark:text-gray-400">예상 변동성</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                {recommendation.expected_volatility_pct != null
                  ? fmtPct(recommendation.expected_volatility_pct)
                  : "—"}
              </p>
            </div>
          </div>
          <div className="space-y-1.5">
            {recommendation.recommended_items.map((item) => (
              <div
                key={`${item.ticker}-${item.market}`}
                className="flex items-center justify-between text-xs p-2 rounded-lg bg-gray-50 dark:bg-gray-800"
              >
                <span className="text-gray-700 dark:text-gray-300">{item.name || item.ticker}</span>
                <span className="font-semibold text-gray-900 dark:text-gray-50">
                  {item.weight.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
          {recommendation.note && (
            <p className="text-xs text-gray-400 dark:text-gray-500">{recommendation.note}</p>
          )}
          <button
            type="button"
            onClick={() => createPortfolioMutation.mutate()}
            disabled={createPortfolioMutation.isPending}
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} w-full flex items-center justify-center gap-1.5 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
          >
            {createPortfolioMutation.isPending && <Loader2 size={14} className="animate-spin" />}이
            추천으로 포트폴리오 만들기
          </button>
        </div>
      )}
      {settingsPersisted && recommendation && recommendation.recommended_items.length === 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {recommendation.note ??
            "추천을 계산하지 못했습니다 — 나중에 리밸런싱 탭에서 다시 시도해보세요"}
        </p>
      )}
    </div>
  );
}
