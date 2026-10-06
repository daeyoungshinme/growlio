import { ArrowRight } from "lucide-react";
import type { GoalRecommendation } from "@/api/rebalancing";
import SkeletonCard from "@/components/common/SkeletonCard";
import RecommendationResultPanel from "@/components/rebalancing/RecommendationResultPanel";
import {
  RecommendationNoItems,
  RecommendationSetupCta,
} from "@/components/rebalancing/RecommendationEmptyStates";
import {
  buildOverallApplySection,
  formatRecMetricParts,
  RISK_TOLERANCE_LABELS,
  SETUP_CTA_ACTION_CLASS,
  significantDrift,
  type OverallTargetSelection,
  type RecommendationTabActions,
} from "@/components/rebalancing/recommendationCardModel";

interface Props {
  data: GoalRecommendation | undefined;
  pending: boolean;
  selection: OverallTargetSelection;
  actions: RecommendationTabActions;
  /** 연령대 미설정 시 "연령대 설정하기" — 카드의 추천 설정 모달을 연다. */
  onOpenOptions: () => void;
}

/** "연령대" 탭 — 나이 구간별 리스크 성향 + 주식비중 상/하한 재배분 추천. 탭 선택 시 지연 로딩된다. */
export default function RecommendationAgeTab({
  data,
  pending,
  selection,
  actions,
  onOpenOptions,
}: Props) {
  if (!data) return pending ? <SkeletonCard rows={2} /> : null;

  if (!data.is_configured) {
    return (
      <RecommendationSetupCta
        note={data.note}
        fallback="연령대를 설정하면 연령대별 추천을 받을 수 있습니다"
        action={
          <button type="button" onClick={onOpenOptions} className={SETUP_CTA_ACTION_CLASS}>
            연령대 설정하기 <ArrowRight size={12} />
          </button>
        }
      />
    );
  }

  if (data.recommended_items.length === 0) return <RecommendationNoItems note={data.note} />;

  return (
    <>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        {[
          `${data.age_bracket} 기준 투자성향 ${RISK_TOLERANCE_LABELS[data.risk_tolerance] ?? data.risk_tolerance}`,
          ...formatRecMetricParts(data),
        ].join(" · ")}
      </p>

      <RecommendationResultPanel
        drift={significantDrift(data.recommended_items, selection.confirmTarget)}
        items={data.recommended_items}
        note={data.note}
        marketSignalLevel={data.market_signal_level}
        extraNoticeAfterWeightList={
          data.includes_cash_equivalent ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              현금성 자산(CMA·파킹통장 등) 합성 비중이 포함되어 있어요 — 실제 계좌와 연결해 목표
              비중에 반영해주세요.
            </p>
          ) : undefined
        }
        suggestedCandidates={data.suggested_candidates}
        onAddSuggested={() => actions.onAddSuggested(data.suggested_candidates)}
        addPending={actions.addPending}
        applySection={buildOverallApplySection(
          selection,
          actions,
          data.recommended_items,
          "연령대별 추천 포트폴리오",
        )}
      />
    </>
  );
}
