import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { isOverseasMarket } from "@/constants/markets";
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
export function isTradableItem(item: RebalancingItem): boolean {
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
