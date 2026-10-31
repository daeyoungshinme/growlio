import type { ExecutionOrderItem, RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { DOMESTIC_MARKETS, isOverseasMarket } from "@/constants/markets";
import { CASH_EQUIVALENT_TICKER, CASH_TICKER, KR_PROPERTY_MARKET } from "@/constants/assets";

export const TRADING_FEE_RATE = 0.00014; // 0.014% 수수료 (한국투자증권 기준)

/** 지정가(현지 통화) 1주의 원화 환산 — 해외는 USD×환율, 환율을 아직 못 받았으면 입력값 그대로. */
export function limitPriceKrw(nativePrice: number, market: string, usdRate: number | null): number {
  return isOverseasMarket(market) && usdRate != null ? nativePrice * usdRate : nativePrice;
}

/** 지정가 주문 예상 원화 금액(1주 환산 × 수량) — 주문표·가격 입력칸·모바일 카드가 같은 값을 보여야 한다. */
export function estimateLimitKrw(
  nativePrice: number,
  qty: number,
  market: string,
  usdRate: number | null,
): number {
  return limitPriceKrw(nativePrice, market, usdRate) * qty;
}

/** 지수 그룹 행(plans/74)인지 — 그룹 행 자체는 수량이 없고 members가 매매 단위다. */
export function isGroupItem(item: RebalancingItem): boolean {
  return !!item.group_key;
}

/** 그룹 행을 매매가 있는 멤버 행으로 펼친다(그 외 항목은 그대로) — 백엔드 `group_expansion.iter_trade_items`와 같은 규칙.
 *  주문·거래 요약은 종목 단위여야 하므로 analysis.items 대신 이 결과를 쓴다. */
export function flattenTradeItems(items: RebalancingItem[]): RebalancingItem[] {
  return items.flatMap((i) =>
    isGroupItem(i)
      ? (i.members ?? []).filter((m) => m.target_value_krw !== m.current_value_krw)
      : [i],
  );
}

/** 실행 화면에서 주문을 낼 수 있는 종목 행 — 현금·현금성 자산·부동산과 1주 미만 차이는 뺀다.
 *  (실행 훅과 가격 조회 훅이 함께 써서 여기 둔다 — 훅끼리 서로 import하면 순환이 생긴다, plans/78 C6) */
export function getActionableItems(analysis: RebalancingAnalysis): RebalancingItem[] {
  return flattenTradeItems(analysis.items).filter(
    (i) =>
      i.ticker !== CASH_TICKER &&
      i.ticker !== CASH_EQUIVALENT_TICKER &&
      i.market !== KR_PROPERTY_MARKET &&
      i.shares_to_trade !== null &&
      Math.abs(i.shares_to_trade) >= 1,
  );
}

/** 해외 종목을 살 수 없는 절세 계좌 — 백엔드 `TAX_DEFERRED_TAX_TYPES`와 같은 집합 */
const TAX_DEFERRED_TAX_TYPES = new Set(["ISA", "PENSION_SAVINGS", "IRP"]);

function isDomesticMarket(market: string): boolean {
  return DOMESTIC_MARKETS.includes(market.toUpperCase());
}

/** 그룹 행 중 매수할 금액이 있고 대표 종목이 해외인 것의 (그룹, 대표, 국내 대체) — 대체 후보 계산용 */
function overseasPrimaryBuyGroups(items: RebalancingItem[]) {
  return items.flatMap((g) => {
    if (!isGroupItem(g) || g.target_value_krw - g.current_value_krw <= 0) return [];
    const members = g.members ?? [];
    const primary = members.find((m) => m.group_role === "PRIMARY");
    const alt = members.find((m) => m.group_role === "DOMESTIC_ALT");
    if (!primary || !alt || isDomesticMarket(primary.market)) return [];
    return [{ group: g, primary, alt }];
  });
}

/** 국내 대체로 바뀔 수 있는 종목 행 — 실행 화면이 대표 종목과 함께 시세를 미리 받는다 */
export function domesticAltCandidates(analysis: RebalancingAnalysis): RebalancingItem[] {
  return overseasPrimaryBuyGroups(analysis.items).map(({ alt }) => alt);
}

/**
 * 매수 계좌가 ISA·연금이면 해외 대표 종목 매수 행을 그룹의 국내 대체 종목 행으로 바꾼다.
 * 백엔드 `group_expansion._buy_target`/`allocate_group_trades`와 같은 규칙 — 그룹 금액 차이만큼 대체 종목을 산다.
 * 해당 없거나(일반 계좌·국내 대표·대체 없음) 대체 종목 시세가 없거나 1주도 못 사면 원래 행을 그대로 돌려준다.
 */
export function buyItemForAccount(
  item: RebalancingItem,
  items: RebalancingItem[],
  taxType: string | undefined,
): RebalancingItem {
  if (!taxType || !TAX_DEFERRED_TAX_TYPES.has(taxType) || item.group_role !== "PRIMARY")
    return item;
  const hit = overseasPrimaryBuyGroups(items).find(({ primary }) => primary.ticker === item.ticker);
  if (!hit) return item;
  const { group, alt } = hit;
  const price = alt.current_price_krw;
  if (!price || price <= 0) return item;
  const diff = group.target_value_krw - group.current_value_krw;
  const targetValue = alt.current_value_krw + diff;
  const targetQty = Math.floor(targetValue / price + 1e-9);
  const shares = targetQty - (alt.current_qty ?? 0);
  if (shares < 1) return item;
  return {
    ...alt,
    target_value_krw: targetValue,
    diff_krw: diff,
    target_qty: targetQty,
    shares_to_trade: shares,
    substitute_for: item.ticker,
  };
}

/**
 * 이 계좌에서 살 수 있는 종목인지 — ISA·연금은 해외 상장 종목을 직접 살 수 없다(국내 대체로 바뀌면 가능).
 * "이 계좌에 매수 종목 추가" 목록이 거부될 주문을 만들지 않게 거른다(plans/80 A2).
 */
export function canBuyInAccount(
  item: RebalancingItem,
  items: RebalancingItem[],
  taxType: string | undefined,
): boolean {
  if (!taxType || !TAX_DEFERRED_TAX_TYPES.has(taxType) || !isOverseasMarket(item.market))
    return true;
  return buyItemForAccount(item, items, taxType) !== item;
}

/**
 * 매수 행 수량을 원래(대표) 종목 주수로 환산 — 대체 종목 행과 대표 종목 행을 함께 배분할 때 단위를 맞춘다.
 * 대체 행이 아니거나 시세가 없으면 그대로 돌려준다.
 */
export function qtyInOriginalUnits(
  row: RebalancingItem,
  original: RebalancingItem,
  qty: number,
): number {
  const rowPrice = row.current_price_krw;
  const origPrice = original.current_price_krw;
  if (row === original || !rowPrice || !origPrice) return qty;
  return Math.round((qty * rowPrice) / origPrice);
}

export type OrderSide = "buy" | "sell";

/** 실행 화면 주문 행 키(선택·수량·지정가 상태의 키) — `${side}_${ticker}_${accountId}` */
export function orderKey(side: OrderSide, ticker: string, accountId: string): string {
  return `${side}_${ticker}_${accountId}`;
}

// 반올림된 주수 기준 실제 거래금액 — 요약·거래계획·거래비용 전체에서 동일하게 사용
export function calcTradeKrw(item: RebalancingItem): number {
  if (item.shares_to_trade !== null && item.current_price_krw && item.current_price_krw > 0) {
    return Math.abs(Math.round(item.shares_to_trade)) * item.current_price_krw;
  }
  return Math.abs(item.diff_krw);
}

// 부호 포함 실제 거래금액 — 상세내역 DiffCell과 거래 계획 금액을 일치시키기 위해 사용
export function calcSignedTradeKrw(item: RebalancingItem): number {
  if (item.shares_to_trade !== null && item.current_price_krw && item.current_price_krw > 0) {
    return (
      Math.sign(item.diff_krw) * Math.abs(Math.round(item.shares_to_trade)) * item.current_price_krw
    );
  }
  return item.diff_krw;
}

// 증권사에 실제 매수/매도 주문이 가능한 항목인지 판별 — CASH/CASH_EQUIVALENT/KR_PROPERTY 등은
// 백엔드가 shares_to_trade를 항상 null로 반환하므로 이 필터로 거래 계획·요약 합계에서 제외한다.
/** 매매 가능 항목 — true면 `shares_to_trade`·`current_price_krw`가 값이 있음을 타입으로도 좁힌다 */
export function isTradableItem(
  item: RebalancingItem,
): item is RebalancingItem & { shares_to_trade: number; current_price_krw: number } {
  return item.shares_to_trade !== null && !!item.current_price_krw && item.current_price_krw > 0;
}

// 요약 카드("매수 필요"/"매도 예상")용 합계 — 거래 불가 항목(현금·부동산 등)의 diff_krw가
// 섞여 "리밸런싱 후 예수금"이 실제와 무관하게 음수로 표시되는 것을 방지하기 위해
// 거래 계획 표(RebalancingTradePlanPanel)와 동일한 항목 집합(isTradableItem)으로 계산한다.
export function calcTradeSummary(items: RebalancingItem[]): {
  totalBuySummary: number;
  totalSellSummary: number;
} {
  const tradableItems = flattenTradeItems(items).filter(isTradableItem);
  const totalBuySummary = tradableItems
    .filter((i) => i.diff_krw > 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  const totalSellSummary = tradableItems
    .filter((i) => i.diff_krw < 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  return { totalBuySummary, totalSellSummary };
}

/** 지정가가 현재가에서 이만큼(%) 넘게 벗어나면 확인창에서 강조 — 오타(0 하나 더/덜)를 잡는 용도 */
export const LIMIT_DEVIATION_WARN_PCT = 5;
/** 지정가의 현재가 대비 이탈률(%) — 현재가를 모르면 null */
export function limitDeviationPct(
  order: ExecutionOrderItem,
  livePricesKrw: Record<string, number>,
  livePricesUsd: Record<string, number>,
): number | null {
  if (order.order_type !== "LIMIT" || !order.limit_price) return null;
  const live = isOverseasMarket(order.market)
    ? livePricesUsd[order.ticker]
    : livePricesKrw[order.ticker];
  if (!live || live <= 0) return null;
  return ((order.limit_price - live) / live) * 100;
}
