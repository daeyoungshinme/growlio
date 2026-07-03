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
