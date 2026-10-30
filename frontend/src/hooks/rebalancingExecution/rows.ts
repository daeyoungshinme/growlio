import type { AssetAccount } from "@/api/assets";
import type { RebalancingAnalysis, RebalancingItem } from "@/api/rebalancing";
import { isOverseasMarket } from "@/constants/markets";
import { isOrderExecutableAccount } from "@/utils/accounts";
import {
  buyItemForAccount,
  flattenTradeItems,
  orderKey,
} from "@/components/rebalancing/rebalancingTradeMath";
import type { ExecutionState } from "./types";

// 실행 훅의 행·대금 계산 — 순수 함수로 두어 useMemo deps가 실제 입력과 일치하게 한다(plans/98 C)

export interface HoldingsInput {
  analysis: RebalancingAnalysis;
  liveBalances: ExecutionState["liveBalances"];
  overseasUnknown: ExecutionState["overseasUnknown"];
}

export interface TradeRowsInput extends HoldingsInput {
  actionableItems: RebalancingItem[];
  tradableAccounts: AssetAccount[];
}

export type PriceInput = Pick<
  ExecutionState,
  "orderType" | "limitPriceOverrides" | "livePricesKrw" | "livePricesUsd" | "globalUsdRate"
>;

export interface TradeRow {
  item: RebalancingItem;
  currentQty: number;
  suggestedQty: number;
}

// 해외 잔고 조회가 실패한 계좌의 해외 종목은 실시간 잔고에 없다 — 없음(0주)으로 보면 매도 행이 사라진다
function hasLiveBalanceFor(h: HoldingsInput, ticker: string, accountId: string): boolean {
  if (!h.liveBalances[accountId]) return false;
  if (!h.overseasUnknown[accountId]) return true;
  const market = flattenTradeItems(h.analysis.items).find((i) => i.ticker === ticker)?.market ?? "";
  return !isOverseasMarket(market);
}

export function getAccountQuantity(h: HoldingsInput, ticker: string, accountId: string): number {
  const livePos = hasLiveBalanceFor(h, ticker, accountId)
    ? h.liveBalances[accountId]?.find((p) => p.ticker === ticker)
    : undefined;
  if (livePos !== undefined) return livePos.quantity;
  return (
    (h.analysis.ticker_account_map[ticker] ?? []).find((a) => a.account_id === accountId)
      ?.quantity ?? 0
  );
}

function accountHoldsTicker(h: HoldingsInput, ticker: string, accountId: string): boolean {
  if (hasLiveBalanceFor(h, ticker, accountId)) {
    return (h.liveBalances[accountId] ?? []).some((p) => p.ticker === ticker && p.quantity > 0);
  }
  return (h.analysis.ticker_account_map[ticker] ?? []).some(
    (a) => a.account_id === accountId && isOrderExecutableAccount(a.asset_type) && a.quantity > 0,
  );
}

export function getLimitPriceNative(
  p: PriceInput,
  key: string,
  ticker: string,
  market: string,
): number {
  const raw =
    key in p.limitPriceOverrides
      ? (p.limitPriceOverrides[key] ?? 0)
      : isOverseasMarket(market)
        ? (p.livePricesUsd[ticker] ?? 0)
        : (p.livePricesKrw[ticker] ?? 0);
  // 해외 주문 지정가는 센트 단위(소수점 2자리)까지만 허용 — Yahoo 등 원본 시세의 부동소수점 오차 제거.
  return isOverseasMarket(market) ? Math.round(raw * 100) / 100 : raw;
}

// 시장가 주문의 결과·이력 "가격" 칸용 참고 시세(시장 통화 — 해외 USD). 브로커에는 보내지 않는다(plans/90 B7)
export function referencePriceNative(p: PriceInput, ticker: string, market: string): number | null {
  const raw = isOverseasMarket(market) ? p.livePricesUsd[ticker] : p.livePricesKrw[ticker];
  if (raw == null || raw <= 0) return null;
  return isOverseasMarket(market) ? Math.round(raw * 100) / 100 : raw;
}

export function getEstimateKrw(
  p: PriceInput,
  key: string,
  ticker: string,
  market: string,
  qty: number,
): number | null {
  if (p.orderType === "LIMIT") {
    const native = getLimitPriceNative(p, key, ticker, market);
    if (native <= 0) return null;
    if (isOverseasMarket(market))
      return p.globalUsdRate != null ? native * p.globalUsdRate * qty : null;
    return native * qty;
  }
  const priceKrw = p.livePricesKrw[ticker] ?? null;
  return priceKrw != null ? priceKrw * qty : null;
}

// 이 계좌에서 실제로 사는 종목 행 — ISA·연금이면 해외 대표 종목 대신 국내 대체 종목(plans/79 E).
// 계좌마다 따로 판단한다: 여러 계좌로 나눠 살 때도 절세 계좌 행은 대체 종목이어야 증권사가 받는다(plans/80 A1)
export function buyRowItem(
  analysis: RebalancingAnalysis,
  tradableAccounts: AssetAccount[],
  item: RebalancingItem,
  accountId: string,
): RebalancingItem {
  const taxType = tradableAccounts.find((a) => a.id === accountId)?.tax_type;
  return buyItemForAccount(item, analysis.items, taxType);
}

export function getSellRows(input: TradeRowsInput, accountId: string): TradeRow[] {
  const rows: TradeRow[] = [];
  for (const item of input.actionableItems) {
    if ((item.shares_to_trade ?? 0) >= 0) continue;
    if (!accountHoldsTicker(input, item.ticker, accountId)) continue;
    const currentQty = getAccountQuantity(input, item.ticker, accountId);
    if (currentQty <= 0) continue;
    const allKisQty = input.tradableAccounts.reduce(
      (sum, acc) => sum + getAccountQuantity(input, item.ticker, acc.id),
      0,
    );
    const totalSuggested = Math.abs(Math.round(item.shares_to_trade ?? 0));
    const suggested =
      allKisQty > 0 ? Math.round((totalSuggested * currentQty) / allKisQty) : totalSuggested;
    // 수동 계좌 등 주문 불가 계좌 보유분까지 합친 매도 권장량이 이 계좌 보유량을 넘을 수 있다
    const capped = Math.min(suggested, currentQty);
    if (capped > 0) rows.push({ item, currentQty, suggestedQty: capped });
  }
  return rows;
}

export function getBuyRows(
  input: TradeRowsInput,
  buyAccounts: ExecutionState["buyAccounts"],
  accountId: string,
): TradeRow[] {
  return input.actionableItems
    .filter(
      (i) => (i.shares_to_trade ?? 0) > 0 && (buyAccounts[i.ticker] ?? []).includes(accountId),
    )
    .map((i) => {
      const item = buyRowItem(input.analysis, input.tradableAccounts, i, accountId);
      const suggestedQty = Math.abs(Math.round(item.shares_to_trade ?? 0));
      return { item, suggestedQty, currentQty: getAccountQuantity(input, item.ticker, accountId) };
    });
}

/**
 * 실제로 나갈 주문 수량. 매도는 보유량을 넘길 수 없다(백엔드도 잘라 낸다) — 수량 입력·일괄 조정은
 * 상한을 걸지 않고, 잔고를 새로 받으면 보유량이 줄 수 있어서 주문·현금 계산 모두 여기서 자른다.
 */
export function effectiveQty(
  side: "sell" | "buy",
  row: TradeRow,
  override: number | undefined,
): number {
  const qty = override ?? row.suggestedQty;
  return side === "sell" ? Math.min(qty, row.currentQty) : qty;
}

/** 한 계좌의 선택된 행 예상 대금 합(원화). 시세를 모르는 행이 하나라도 있으면 null. */
export function sumSelectedEstimates(
  p: PriceInput,
  rows: TradeRow[],
  side: "sell" | "buy",
  accountId: string,
  selected: Set<string>,
  qtyOverrides: Record<string, number>,
): number | null {
  let total = 0;
  for (const row of rows) {
    const key = orderKey(side, row.item.ticker, accountId);
    if (!selected.has(key)) continue;
    const qty = effectiveQty(side, row, qtyOverrides[key]);
    const est = getEstimateKrw(p, key, row.item.ticker, row.item.market, qty);
    if (est === null) return null;
    total += est;
  }
  return total;
}
