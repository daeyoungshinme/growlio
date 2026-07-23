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

export interface WeightDiffRow {
  key: string;
  name: string;
  ticker: string;
  market: string;
  /** null이면 현재 포트폴리오에는 없는 신규 후보. */
  currentWeight: number | null;
  /** null이면 추천에서 빠진(비중 0) 기존 종목. */
  recommendedWeight: number | null;
}

/** 추천 비중과 현재 포트폴리오 목표 비중을 합쳐 "적용 전 비교 미리보기" 테이블 행을 만든다 —
 * `computeRecommendationDrift`가 요약 수치(최대 차이·신규 후보 개수)만 내는 것과 달리, 종목별
 * 전체 비교(현재 vs 추천 vs 차이)를 보여주기 위함. 추천 비중 기준 내림차순 정렬. */
export function buildWeightDiffRows(
  recommended: GoalRecommendationItem[],
  current: PortfolioItem[],
): WeightDiffRow[] {
  const rows = new Map<string, WeightDiffRow>();

  for (const item of current) {
    rows.set(itemKey(item), {
      key: itemKey(item),
      name: item.name,
      ticker: item.ticker,
      market: item.market,
      currentWeight: item.weight,
      recommendedWeight: null,
    });
  }

  for (const item of recommended) {
    const key = itemKey(item);
    const existing = rows.get(key);
    if (existing) {
      existing.recommendedWeight = item.weight;
    } else {
      rows.set(key, {
        key,
        name: item.name,
        ticker: item.ticker,
        market: item.market,
        currentWeight: null,
        recommendedWeight: item.weight,
      });
    }
  }

  return Array.from(rows.values()).sort(
    (a, b) => (b.recommendedWeight ?? 0) - (a.recommendedWeight ?? 0),
  );
}
