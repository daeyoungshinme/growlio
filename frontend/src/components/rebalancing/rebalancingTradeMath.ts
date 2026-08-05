import { RebalancingItem } from "@/api/rebalancing";

export const TRADING_FEE_RATE = 0.00014; // 0.014% 수수료 (한국투자증권 기준)

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
  const tradableItems = items.filter(isTradableItem);
  const totalBuySummary = tradableItems
    .filter((i) => i.diff_krw > 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  const totalSellSummary = tradableItems
    .filter((i) => i.diff_krw < 0)
    .reduce((s, i) => s + calcTradeKrw(i), 0);
  return { totalBuySummary, totalSellSummary };
}
