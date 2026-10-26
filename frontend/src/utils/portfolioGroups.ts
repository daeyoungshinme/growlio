import type {
  IndexGroupSuggestion,
  PortfolioGroupMember,
  PortfolioItem,
  PortfolioItemGroup,
} from "@/api/portfolios";
import { isOverseasMarket } from "@/constants/markets";

/** 지수 그룹 항목(plans/74) 편집 순수 함수 — 편집기(usePortfolioItemsEditor)가 사용한다. */

type Keyed = { ticker: string; market: string };

const keyOf = (m: Keyed) => `${m.ticker}|${m.market}`;
const sameKey = (a: Keyed, b: Keyed) => a.ticker === b.ticker && a.market === b.market;
const toMember = ({
  ticker,
  market,
  name,
  leverage,
}: PortfolioGroupMember): PortfolioGroupMember => ({
  ticker,
  market,
  name,
  ...(leverage && leverage > 1 ? { leverage } : {}),
});

/** 레버리지 멤버인지 — 대표·국내 대체 매수 종목은 1배만 가능하다(백엔드 검증과 같은 규칙). */
export const isLeveraged = (m: { leverage?: number | null }) => (m.leverage ?? 1) > 1;

/** 분석 대상 밖 계좌에만 있는 제안 멤버의 (ticker|market) → 보유 계좌 이름 — 제안은 전체 계좌 기준이다. */
export function outOfScopeAccounts(
  suggestion: IndexGroupSuggestion | undefined,
): Map<string, string[]> {
  return new Map(
    (suggestion?.members ?? [])
      .filter((m) => m.in_scope === false)
      .map((m) => [keyOf(m), m.account_names ?? []]),
  );
}

/** "QLD ×2(해외)" — 범위 밖 계좌 이름을 붙인 표시명. */
export const scopedMemberLabel = (m: PortfolioGroupMember, accounts: string[] | undefined) =>
  `${memberLabel(m)}${accounts ? `(${accounts.join("·") || "다른 계좌"})` : ""}`;

/** 칩·목록 표시용 이름 — 레버리지면 "QLD ×2". */
export const memberLabel = (m: PortfolioGroupMember) =>
  `${m.name || m.ticker}${isLeveraged(m) ? ` ×${m.leverage}` : ""}`;

/** 그룹 항목에 속한 모든 종목(대표·멤버·국내 대체). */
export function groupKeys(item: PortfolioItem): Keyed[] {
  if (!item.group) return [item];
  return [
    item,
    ...item.group.members,
    ...(item.group.domestic_alt ? [item.group.domestic_alt] : []),
  ];
}

/** 제안을 그룹 항목으로 적용 — 같은 지수의 단독 행·같은 키의 기존 그룹은 합쳐지고 비중도 합산된다.
 *  새 그룹은 합쳐진 첫 행 자리에 들어간다(없으면 맨 끝, 비중 0). */
export function applyIndexGroup(
  items: PortfolioItem[],
  suggestion: IndexGroupSuggestion,
): PortfolioItem[] {
  const keys = new Set(
    [
      suggestion.primary,
      ...suggestion.members,
      ...(suggestion.domestic_alt ? [suggestion.domestic_alt] : []),
    ].map(keyOf),
  );
  const absorbed = (it: PortfolioItem) =>
    it.group ? it.group.key === suggestion.key : keys.has(keyOf(it));
  const firstIdx = items.findIndex(absorbed);
  const weight =
    Math.round(items.filter(absorbed).reduce((s, it) => s + (Number(it.weight) || 0), 0) * 10) / 10;
  const alt = suggestion.domestic_alt;
  const group: PortfolioItemGroup = {
    key: suggestion.key,
    label: suggestion.label,
    members: suggestion.members
      .filter((m) => !sameKey(m, suggestion.primary) && !(alt && sameKey(m, alt)))
      .map(toMember),
    domestic_alt: alt ? toMember(alt) : null,
  };
  const groupItem: PortfolioItem = {
    ticker: suggestion.primary.ticker,
    market: suggestion.primary.market,
    name: suggestion.primary.name,
    weight,
    group,
  };
  const rest = items.filter((it) => !absorbed(it));
  const insertAt =
    firstIdx < 0 ? rest.length : items.slice(0, firstIdx).filter((it) => !absorbed(it)).length;
  return [...rest.slice(0, insertAt), groupItem, ...rest.slice(insertAt)];
}

/** 묶음 해제 — 대표 종목 단독 행으로 되돌린다(비중 유지). */
export function ungroupItem(item: PortfolioItem): PortfolioItem {
  return { ticker: item.ticker, market: item.market, name: item.name, weight: item.weight };
}

/** 대표 매수 종목 교체 — 이전 대표는 멤버로 남겨 계속 합산한다. 대표가 국내 상장이면 국내 대체 종목은 필요 없다. */
export function setGroupPrimary(item: PortfolioItem, next: PortfolioGroupMember): PortfolioItem {
  if (!item.group || sameKey(item, next)) return item;
  const prev = toMember(item);
  const oldAlt = item.group.domestic_alt ?? null;
  const keepAlt = isOverseasMarket(next.market) && oldAlt && !sameKey(oldAlt, next) ? oldAlt : null;
  const members = [
    ...item.group.members,
    prev,
    ...(oldAlt && !keepAlt && !sameKey(oldAlt, next) ? [oldAlt] : []),
  ]
    .filter((m) => !sameKey(m, next))
    .map(toMember);
  return {
    ...item,
    ticker: next.ticker,
    market: next.market,
    name: next.name,
    group: { ...item.group, members, domestic_alt: keepAlt },
  };
}

/** 국내 대체 매수 종목 교체(null이면 없음) — 이전 대체 종목은 멤버로 남겨 계속 합산한다. */
export function setGroupDomesticAlt(
  item: PortfolioItem,
  next: PortfolioGroupMember | null,
): PortfolioItem {
  if (!item.group) return item;
  const oldAlt = item.group.domestic_alt;
  const members = [...item.group.members, ...(oldAlt ? [oldAlt] : [])]
    .filter((m) => !(next && sameKey(m, next)))
    .map(toMember);
  return { ...item, group: { ...item.group, members, domestic_alt: next ? toMember(next) : null } };
}

/** 멤버 하나를 그룹에서 뺀다 — 뺀 종목은 목표 외 보유 종목으로 돌아간다. */
export function removeGroupMember(item: PortfolioItem, member: Keyed): PortfolioItem {
  if (!item.group) return item;
  return {
    ...item,
    group: { ...item.group, members: item.group.members.filter((m) => !sameKey(m, member)) },
  };
}
