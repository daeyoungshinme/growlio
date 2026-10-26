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

/** 추천 종목 중 포트폴리오 지수 그룹(plans/74)에 속한 종목은 그 그룹(대표 종목 키)으로 합산한다 —
 * 그룹 항목은 대표 종목 키 하나로 목표 비중을 가지므로, 같은 지수의 다른 종목(예: SPY ↔ 그룹 대표 VOO)을
 * "신규 후보"로 세지 않기 위함. 백엔드 `goal_recommendation_service.fold_into_portfolio_groups()`와 같은 규칙. */
export function foldIntoPortfolioGroups(
  recommended: GoalRecommendationItem[],
  current: PortfolioItem[],
): GoalRecommendationItem[] {
  const owner = new Map<string, PortfolioItem>();
  for (const item of current) {
    if (!item.group) continue;
    owner.set(itemKey(item), item);
    for (const m of item.group.members) owner.set(itemKey(m), item);
    if (item.group.domestic_alt) owner.set(itemKey(item.group.domestic_alt), item);
  }
  if (!owner.size) return recommended;
  const folded = new Map<string, GoalRecommendationItem>();
  for (const rec of recommended) {
    const group = owner.get(itemKey(rec));
    const target = group
      ? { ...rec, ticker: group.ticker, market: group.market, name: group.name }
      : rec;
    const key = itemKey(target);
    const existing = folded.get(key);
    folded.set(key, existing ? { ...existing, weight: existing.weight + rec.weight } : target);
  }
  return Array.from(folded.values());
}

/** 추천 비중을 저장용 항목으로 바꾸면서 현재 포트폴리오의 지수 그룹은 유지한다 — 추천이 그룹 멤버를 내면
 * 그룹 비중으로 합산하고, 대표 종목 키가 같은 행에 그룹 정보를 다시 붙인다(전체 교체 저장으로 그룹이 사라지지 않게). */
export function toPortfolioItemsPreservingGroups(
  recommended: GoalRecommendationItem[],
  current: PortfolioItem[],
): PortfolioItem[] {
  const groupByKey = new Map(current.filter((i) => i.group).map((i) => [itemKey(i), i.group]));
  return normalizeWeights(foldIntoPortfolioGroups(recommended, current)).map((item) => {
    const group = groupByKey.get(itemKey(item));
    return group ? { ...item, group } : item;
  });
}

/** 추천 비중(recommended)과 현재 포트폴리오 목표 비중(current)을 ticker+market 기준으로 비교한다.
 * 사용자가 마지막으로 추천을 적용한 직후에는 두 값이 동일하고, 이후 시장 데이터가 바뀌어 추천이
 * 달라지거나 사용자가 수동으로 비중을 편집하면 차이가 발생한다. */
export function computeRecommendationDrift(
  recommended: GoalRecommendationItem[],
  current: PortfolioItem[],
): RecommendationDrift {
  recommended = foldIntoPortfolioGroups(recommended, current);
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
  recommended = foldIntoPortfolioGroups(recommended, current);
  const rows = new Map<string, WeightDiffRow>();

  for (const item of current) {
    rows.set(itemKey(item), {
      key: itemKey(item),
      name: item.group?.label || item.name,
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

/** 추천 비중을 포트폴리오 저장용 항목으로 변환한다 — 소수 첫째 자리로 반올림하고, 반올림 오차로
 * 합계가 100에서 벗어나면 그 차이를 마지막 항목에 몰아 백엔드 합계=100 검증을 통과시킨다. */
export function normalizeWeights(items: GoalRecommendationItem[]): PortfolioItem[] {
  const normalized = items.map((i) => ({
    ticker: i.ticker,
    name: i.name,
    market: i.market,
    weight: Math.round(i.weight * 10) / 10,
  }));
  const diff = Math.round((100 - normalized.reduce((s, i) => s + i.weight, 0)) * 10) / 10;
  if (normalized.length > 0 && diff !== 0) normalized[normalized.length - 1].weight += diff;
  return normalized;
}
