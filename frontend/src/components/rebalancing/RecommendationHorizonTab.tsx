import type { HorizonGoalRecommendation } from "@/api/rebalancing";
import type { Portfolio } from "@/api/portfolios";
import {
  ACCOUNT_TAX_TYPE_LABELS,
  INVESTMENT_HORIZON_LABELS,
  type AccountTaxType,
  type AssetAccount,
  type InvestmentHorizon,
} from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { normalizeWeights } from "@/utils/recommendationDrift";
import SkeletonCard from "@/components/common/SkeletonCard";
import RecommendationResultPanel from "@/components/rebalancing/RecommendationResultPanel";
import {
  RISK_TOLERANCE_LABELS,
  significantDrift,
  type RecommendationTabActions,
} from "@/components/rebalancing/recommendationCardModel";

interface Props {
  horizon: InvestmentHorizon;
  taxType: AccountTaxType;
  /** 선택된 (기간, 세제유형) 콤보의 추천 — 아직 로딩 전이면 undefined */
  rec: HorizonGoalRecommendation | undefined;
  fetching: boolean;
  /** 태그 매칭으로 확정된 적용 대상 포트폴리오(없으면 안내 문구만) */
  targetPortfolio: Portfolio | undefined;
  /** 같은 기간·세제유형 태그의 주식 계좌 — "새 포트폴리오 만들기" 시 함께 연결 */
  stockAccounts: AssetAccount[];
  /** 같은 기간·세제유형 태그의 CMA/파킹통장 — 현금성 자산 추천의 실제 근거 계좌 */
  cashEquivalentMatches: AssetAccount[];
  actions: RecommendationTabActions;
}

/** "단기"/"중기"/"장기" 탭 — 계좌 태그 기반 고정 리스크 성향 추천. 적용 대상은 태그 매칭 포트폴리오
 * 하나로 확정되며, 현금성 자산이 포함된 추천은 매칭 CMA/파킹통장이 있어야만 적용할 수 있다. */
export default function RecommendationHorizonTab({
  horizon,
  taxType,
  rec,
  fetching,
  targetPortfolio,
  stockAccounts,
  cashEquivalentMatches,
  actions,
}: Props) {
  if (!rec) return fetching ? <SkeletonCard rows={2} /> : null;

  const hasItems = rec.recommended_items.length > 0;
  const cashUnmatched = rec.includes_cash_equivalent && cashEquivalentMatches.length === 0;
  const { onCreatePortfolio } = actions;

  return (
    <>
      <p className="text-xs text-gray-600 dark:text-gray-300">
        {INVESTMENT_HORIZON_LABELS[horizon]} · {ACCOUNT_TAX_TYPE_LABELS[taxType]} 태그 계좌{" "}
        {rec.account_count}개 · 자산총액 {fmtKrw(rec.base_krw)} · 투자성향{" "}
        {RISK_TOLERANCE_LABELS[rec.risk_tolerance] ?? rec.risk_tolerance}
        {rec.required_dividend_yield_pct != null &&
          ` · 목표 배당수익률 연 ${rec.required_dividend_yield_pct.toFixed(1)}%`}
        {hasItems &&
          rec.expected_return_pct != null &&
          ` · 기대수익률 ${rec.expected_return_pct.toFixed(1)}%`}
        {hasItems &&
          rec.expected_dividend_yield_pct != null &&
          ` · 배당수익률 약 ${rec.expected_dividend_yield_pct.toFixed(1)}%`}
        {hasItems &&
          rec.expected_volatility_pct != null &&
          ` · 예상 변동성 연 ${rec.expected_volatility_pct.toFixed(1)}%`}
      </p>

      {hasItems ? (
        <RecommendationResultPanel
          drift={significantDrift(rec.recommended_items, targetPortfolio)}
          items={rec.recommended_items}
          note={rec.note}
          marketSignalLevel={rec.market_signal_level}
          suggestedCandidates={rec.suggested_candidates}
          onAddSuggested={() => actions.onAddSuggested(rec.suggested_candidates)}
          addPending={actions.addPending}
          extraNoticeBeforeApply={
            cashUnmatched ? (
              <p className="text-xs text-gray-500 dark:text-gray-400 pt-2 border-t border-teal-200 dark:border-teal-800/50">
                현금성 자산(CMA·파킹통장 등)이 포함된 추천이에요 — 계좌 관리에서 CMA/파킹통장 계좌에
                "{INVESTMENT_HORIZON_LABELS[horizon]}" 기간 태그를 지정하면 자동 적용할 수 있어요.
              </p>
            ) : undefined
          }
          applySection={
            cashUnmatched
              ? null
              : {
                  targetPortfolios: targetPortfolio ? [targetPortfolio] : [],
                  selectedTargetId: targetPortfolio?.id ?? "",
                  onSelectTarget: () => {},
                  onApplyClick: actions.onApplyClick,
                  applyPending: actions.applyPending,
                  noTargetMessage:
                    "포트폴리오 탭에서 이 기간·계좌유형에 해당하는 계좌를 태그하고 기준 포트폴리오로 지정하면 추천 비중을 바로 적용할 수 있어요.",
                  extraCopyBeforeButtons: rec.includes_cash_equivalent ? (
                    <p className="text-xs text-teal-600 dark:text-teal-500">
                      현금성 자산 반영을 위해 {cashEquivalentMatches.map((a) => a.name).join(", ")}{" "}
                      계좌가 포트폴리오에 자동으로 연결됩니다.
                    </p>
                  ) : undefined,
                  onCreatePortfolio: onCreatePortfolio
                    ? () =>
                        onCreatePortfolio(
                          normalizeWeights(rec.recommended_items),
                          `${INVESTMENT_HORIZON_LABELS[horizon]} 추천 포트폴리오`,
                          [
                            ...stockAccounts
                              .filter(
                                (a) => a.investment_horizon === horizon && a.tax_type === taxType,
                              )
                              .map((a) => a.id),
                            ...cashEquivalentMatches.map((a) => a.id),
                          ],
                        )
                    : undefined,
                }
          }
        />
      ) : (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {rec.note ?? "추천을 계산할 수 없습니다"}
        </p>
      )}
    </>
  );
}
