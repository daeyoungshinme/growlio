import type { GoalRecommendationItem } from "@/api/rebalancing";
import type { PortfolioItem } from "@/api/portfolios";

/** PORTFOLIO_WEIGHT_TOLERANCE(비중 합계 오차, 0.01%p)보다 유의미하게 큰 값으로,
 * "추천이 달라졌다"고 사용자에게 알릴 만한 차이의 최소 기준. */
export const RECOMMENDATION_DRIFT_THRESHOLD_PCT = 3;

export interface RecommendationDrift {
  /** 현재 포트폴리오에도 있고 추천에도 있는 항목들 중 최대 비중 차이(%p) */
  maxDeltaPct: number;
  /** 추천에는 있지만 현재 포트폴리오엔 없는 신규 후보 개수 */
  newCandidateCount: number;
}

function itemKey(item: { ticker: string; market: string }): string {
  return `${item.ticker}-${item.market}`;
}

/** 추천 비중(recommended)과 현재 포트폴리오 목표 비중(current)을 ticker+market 기준으로 비교한다.
 * 사용자가 마지막으로 추천을 적용한 직후에는 두 값이 동일하고, 이후 시장 데이터가 바뀌어 추천이
 * 달라지거나 사용자가 수동으로 비중을 편집하면 차이가 발생한다. */
export function computeRecommendationDrift(
  recommended: GoalRecommendationItem[],
  current: PortfolioItem[],
): RecommendationDrift {
  const currentWeightByKey = new Map(current.map((item) => [itemKey(item), item.weight]));
  let maxDeltaPct = 0;
  let newCandidateCount = 0;

  for (const item of recommended) {
    const currentWeight = currentWeightByKey.get(itemKey(item));
    if (currentWeight === undefined) {
      newCandidateCount += 1;
      continue;
    }
    maxDeltaPct = Math.max(maxDeltaPct, Math.abs(item.weight - currentWeight));
  }

  return { maxDeltaPct: Math.round(maxDeltaPct * 10) / 10, newCandidateCount };
}

export function hasSignificantDrift(drift: RecommendationDrift): boolean {
  return drift.maxDeltaPct >= RECOMMENDATION_DRIFT_THRESHOLD_PCT || drift.newCandidateCount > 0;
}
