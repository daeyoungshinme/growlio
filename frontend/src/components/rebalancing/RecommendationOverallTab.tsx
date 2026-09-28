import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import type { GoalRecommendation } from "@/api/rebalancing";
import RecommendationResultPanel from "@/components/rebalancing/RecommendationResultPanel";
import {
  buildOverallApplySection,
  significantDrift,
  type OverallTargetSelection,
  type RecommendationTabActions,
} from "@/components/rebalancing/recommendationCardModel";

interface Props {
  data: GoalRecommendation;
  selection: OverallTargetSelection;
  actions: RecommendationTabActions;
}

/** "전체" 탭 — 목표금액·목표연도 역산 추천. 목표 미설정이면 설정 유도 CTA를 보여준다. */
export default function RecommendationOverallTab({ data, selection, actions }: Props) {
  if (!data.is_configured) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {data.note ?? "목표금액·목표연도를 설정하면 추천을 받을 수 있습니다"}
        </p>
        <Link
          to="/invest-plan?tab=적립 계획&from=recommendation"
          className="flex items-center gap-1 text-xs font-semibold text-teal-600 dark:text-teal-400 hover:underline shrink-0"
        >
          목표 설정하러 가기 <ArrowRight size={12} />
        </Link>
      </div>
    );
  }

  if (data.recommended_items.length === 0) {
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {data.note ?? "추천을 계산할 수 없습니다 — 후보 ETF를 등록해주세요"}
      </p>
    );
  }

  return (
    <>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        목표 달성에 필요한 연 수익률 {data.required_return_pct?.toFixed(1)}%
        {data.required_dividend_yield_pct != null &&
          ` · 목표 배당수익률 연 ${data.required_dividend_yield_pct.toFixed(1)}%`}{" "}
        — 아래 비중으로 조정하면 기대수익률 {data.expected_return_pct?.toFixed(1)}% (최근{" "}
        {data.cagr_lookback_years}년 CAGR 기준)
        {data.expected_dividend_yield_pct != null &&
          ` (배당수익률 약 ${data.expected_dividend_yield_pct.toFixed(1)}%)`}
        를 기대할 수 있습니다.
        {data.expected_volatility_pct != null &&
          ` 예상 변동성은 연 ${data.expected_volatility_pct.toFixed(1)}%입니다.`}
      </p>

      <RecommendationResultPanel
        drift={significantDrift(data.recommended_items, selection.confirmTarget)}
        items={data.recommended_items}
        note={data.note}
        marketSignalLevel={data.market_signal_level}
        suggestedCandidates={data.suggested_candidates}
        onAddSuggested={() => actions.onAddSuggested(data.suggested_candidates)}
        addPending={actions.addPending}
        applySection={buildOverallApplySection(
          selection,
          actions,
          data.recommended_items,
          "추천 포트폴리오",
        )}
      />
    </>
  );
}
