import type { CandidateOverlap, OverlapGroup, OverlapMember } from "@/api/rebalancing";
import { DOMESTIC_MARKETS } from "@/constants";

export const itemKey = (ticker: string, market: string) => `${ticker}:${market}`;

/** 총보수(%) 표시 — 국내 S&P500 ETF(0.0068%)처럼 아주 작은 값도 뭉개지지 않게 유효숫자 3자리. */
export function formatTerPct(pct: number): string {
  return `${Number(pct.toPrecision(3))}%`;
}

/** 보수 차이(%p) → 1,000만원 보유 시 연간 비용 차이(원). */
export function annualCostGapPer10M(gapPct: number): number {
  return Math.round((gapPct / 100) * 10_000_000);
}

export function buildTerMap(overlap: CandidateOverlap | undefined): Map<string, number> {
  const map = new Map<string, number>();
  for (const p of overlap?.profiles ?? []) {
    if (p.ter_pct != null) map.set(itemKey(p.ticker, p.market), p.ter_pct);
  }
  return map;
}

/** 비중 가중평균 총보수 — 보수를 모르는 종목은 분모에서 빼고, 보수 확인 비중(coverage)을 함께 준다. */
export function weightedTerPct(
  items: { ticker: string; market: string; weight: number }[],
  terMap: Map<string, number>,
): { pct: number; coveragePct: number } | null {
  let covered = 0;
  let total = 0;
  let sum = 0;
  for (const i of items) {
    total += i.weight;
    const ter = terMap.get(itemKey(i.ticker, i.market));
    if (ter == null) continue;
    covered += i.weight;
    sum += i.weight * ter;
  }
  if (covered <= 0 || total <= 0) return null;
  return { pct: sum / covered, coveragePct: (covered / total) * 100 };
}

/** 추천 결과 화면용 — 추천 비중이 0보다 큰 종목이 하나라도 들어간 그룹만. */
export function groupsTouchingItems(
  groups: OverlapGroup[],
  items: { ticker: string; market: string; weight: number }[],
): OverlapGroup[] {
  const recommended = new Set(
    items.filter((i) => i.weight > 0).map((i) => itemKey(i.ticker, i.market)),
  );
  return groups.filter((g) => g.members.some((m) => recommended.has(itemKey(m.ticker, m.market))));
}

/** 같은 그룹 안에 상장 시장(국내/해외)이 섞였는지 — 이 경우 세금·환전 비용이 달라 보수만으로 비교하기 어렵다. */
export function isMixedListing(group: OverlapGroup): boolean {
  const domestic = group.members.map((m) => DOMESTIC_MARKETS.includes(m.market.toUpperCase()));
  return domestic.some(Boolean) && domestic.some((d) => !d);
}

export function reasonLabel(group: OverlapGroup): string {
  const parts: string[] = [];
  if (group.reasons.includes("SAME_INDEX")) parts.push("같은 지수");
  if (group.reasons.includes("HIGH_CORR")) {
    parts.push(
      group.max_correlation != null
        ? `움직임 유사 ${group.max_correlation.toFixed(2)}`
        : "움직임 유사",
    );
  }
  return parts.join(" · ");
}

/** 후보 관리 모달의 칩 경고 문구 — 이 종목과 겹치는 다른 멤버(보유 종목 우선)를 짧게 알려준다. */
export function overlapWarningFor(
  overlap: CandidateOverlap | undefined,
  ticker: string,
  market: string,
): string | null {
  const key = itemKey(ticker, market);
  const group = overlap?.groups.find((g) =>
    g.members.some((m) => itemKey(m.ticker, m.market) === key),
  );
  if (!group) return null;
  const others = group.members
    .filter((m) => itemKey(m.ticker, m.market) !== key)
    .sort((a, b) => Number(b.held) - Number(a.held));
  if (others.length === 0) return null;
  const first = others[0];
  const label = `${first.held ? "보유 중인 " : "후보 "}${first.name}`;
  const more = others.length > 1 ? ` 외 ${others.length - 1}개` : "";
  return `${label}${more}와(과) ${reasonLabel(group)}`;
}

export function isCheapest(group: OverlapGroup, m: OverlapMember): boolean {
  return group.cheapest_ticker === m.ticker && group.cheapest_market === m.market;
}
