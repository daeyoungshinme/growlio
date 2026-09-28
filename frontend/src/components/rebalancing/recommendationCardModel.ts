import type { ComponentProps } from "react";
import type {
  GoalRecommendation,
  GoalRecommendationItem,
  HorizonGoalRecommendation,
  PortfolioExpectedMetrics,
  SuggestedGoalCandidate,
} from "@/api/rebalancing";
import type { Portfolio, PortfolioItem } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";
import type RecommendationApplySection from "@/components/rebalancing/RecommendationApplySection";
import {
  computeRecommendationDrift,
  hasSignificantDrift,
  normalizeWeights,
  type RecommendationDrift,
} from "@/utils/recommendationDrift";

/** RecommendationCard와 탭 본문 컴포넌트(전체/연령대/기간별)가 공유하는 타입·순수 로직. */

export const RISK_TOLERANCE_LABELS: Record<string, string> = {
  CONSERVATIVE: "보수적",
  BALANCED: "중립",
  AGGRESSIVE: "공격적",
};

export type CreatePortfolioHandler = (
  items: PortfolioItem[],
  suggestedName: string,
  accountIds?: string[],
) => void;

/** 3개 탭 본문이 공통으로 받는 액션 — 카드가 소유한 뮤테이션/확인창 상태로 연결된다. */
export interface RecommendationTabActions {
  onAddSuggested: (candidates: SuggestedGoalCandidate[]) => void;
  addPending: boolean;
  onApplyClick: () => void;
  applyPending: boolean;
  onCreatePortfolio?: CreatePortfolioHandler;
}

/** 전체/연령대 탭이 공유하는 "어느 포트폴리오에나 적용" 대상 선택 상태. */
export interface OverallTargetSelection {
  targetPortfolios: Portfolio[];
  selectedTargetId: string;
  onSelectTarget: (id: string) => void;
  anchoredTargetIds: string[];
  /** 드리프트 비교·적용 확인 기준 포트폴리오(선택값, 없으면 첫 후보) */
  confirmTarget: Portfolio | undefined;
}

type ApplySectionProps = ComponentProps<typeof RecommendationApplySection>;

/** 대상 포트폴리오 대비 유의미한 추천 변화가 있을 때만 드리프트를 돌려준다(배지 노출용). */
export function significantDrift(
  items: GoalRecommendationItem[],
  target: Portfolio | undefined,
): RecommendationDrift | null {
  if (!target) return null;
  const drift = computeRecommendationDrift(items, target.items);
  return hasSignificantDrift(drift) ? drift : null;
}

/** 전체/연령대 탭의 적용 섹션 — 대상 선택 + 적용 + "새 포트폴리오 만들기"(계좌 연결 없음). */
export function buildOverallApplySection(
  selection: OverallTargetSelection,
  actions: RecommendationTabActions,
  items: GoalRecommendationItem[],
  suggestedName: string,
): ApplySectionProps {
  const { onCreatePortfolio } = actions;
  return {
    targetPortfolios: selection.targetPortfolios,
    selectedTargetId: selection.selectedTargetId,
    onSelectTarget: selection.onSelectTarget,
    anchoredTargetIds: selection.anchoredTargetIds,
    onApplyClick: actions.onApplyClick,
    applyPending: actions.applyPending,
    noTargetMessage:
      "아직 포트폴리오가 없어요. 아래 버튼으로 이 비중 그대로 새 포트폴리오를 만들 수 있어요.",
    onCreatePortfolio: onCreatePortfolio
      ? () => onCreatePortfolio(normalizeWeights(items), suggestedName)
      : undefined,
  };
}

export interface ApplyConfirm {
  target: Portfolio;
  items: GoalRecommendationItem[];
  metrics: PortfolioExpectedMetrics;
  message: string;
  accountIds?: string[];
}

function pickMetrics(d: PortfolioExpectedMetrics): PortfolioExpectedMetrics {
  return {
    expected_return_pct: d.expected_return_pct,
    expected_dividend_yield_pct: d.expected_dividend_yield_pct,
    expected_volatility_pct: d.expected_volatility_pct,
  };
}

const applyMessage = (name: string) =>
  `${name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 리밸런싱 분석이 자동으로 실행됩니다. 계속하시겠습니까?`;

/** 전체/연령대/기간별 3개 탭이 각각 그리던 "적용" 확인창을 하나로 통합 — 현재 탭에 맞는
 * 대상 포트폴리오/추천 데이터/안내 문구를 골라준다(null이면 확인창을 띄우지 않음). */
export function buildApplyConfirm(params: {
  tab: "전체" | "연령대" | "기간별";
  overallData: GoalRecommendation;
  ageData: GoalRecommendation | undefined;
  overallTarget: Portfolio | undefined;
  horizonRec: HorizonGoalRecommendation | undefined;
  horizonTarget: Portfolio | undefined;
  cashEquivalentMatches: AssetAccount[];
}): ApplyConfirm | null {
  const { tab, overallData, ageData, overallTarget, horizonRec, horizonTarget } = params;
  const { cashEquivalentMatches } = params;

  if (tab === "전체" && overallTarget) {
    return {
      target: overallTarget,
      items: overallData.recommended_items,
      metrics: pickMetrics(overallData),
      message: applyMessage(overallTarget.name),
    };
  }
  if (tab === "연령대" && ageData && overallTarget) {
    return {
      target: overallTarget,
      items: ageData.recommended_items,
      metrics: pickMetrics(ageData),
      message: applyMessage(overallTarget.name),
    };
  }
  if (tab === "기간별" && horizonTarget && horizonRec) {
    const withCash = horizonRec.includes_cash_equivalent && cashEquivalentMatches.length > 0;
    const accountIds =
      horizonRec.includes_cash_equivalent && horizonTarget.account_ids?.length
        ? Array.from(
            new Set([...horizonTarget.account_ids, ...cashEquivalentMatches.map((a) => a.id)]),
          )
        : undefined;
    return {
      target: horizonTarget,
      items: horizonRec.recommended_items,
      metrics: pickMetrics(horizonRec),
      accountIds,
      message: withCash
        ? `${horizonTarget.name}의 목표 비중이 추천 비중으로 즉시 업데이트되고, 현금성 자산 반영을 위해 ${cashEquivalentMatches.map((a) => a.name).join(", ")} 계좌가 포트폴리오에 자동으로 연결됩니다. 리밸런싱 분석이 자동으로 실행됩니다. 계속하시겠습니까?`
        : applyMessage(horizonTarget.name),
    };
  }
  return null;
}
