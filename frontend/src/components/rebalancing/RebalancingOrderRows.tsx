import React from "react";
import { RefreshCw } from "lucide-react";
import type { RebalancingItem } from "@/api/rebalancing";
import type { ExecutionAction, OrderType, PriceLoadState } from "@/hooks/useRebalancingExecution";
import { SideBadge } from "./RebalancingBadges";
import { PriceCell } from "./RebalancingPriceCell";
import { RebalancingPriceInput } from "./RebalancingPriceInput";

/** `RebalancingOrderTable`의 행 조각 — 모바일 카드와 데스크톱 표가 같은 행 모델을 쓴다 (plans/79 D3) */

/** 주문 행 하나의 표시값 — 모바일 카드·데스크톱 행이 같은 값을 쓴다 */
export interface OrderRowModel {
  key: string;
  qty: number;
  nativeLimitPrice: number;
  currentNativePrice: number | undefined;
  /** 시장가 예상 원화(지정가면 null일 수 있음) */
  est: number | null;
  /** 지정가 × 수량 원화 환산 */
  estKrw: number;
  /** 같은 종목을 여러 계좌로 나눠 사는 매수 행 */
  isMultiAccount: boolean;
  allocated: number;
  needed: number;
}

export function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-500 bg-gray-100 dark:bg-gray-800/30">
      {children}
    </div>
  );
}

/** 매수 행 보유 안내 — "N주 → 목표 M주" / "현재 N주 보유" / "현재 미보유" */
export function BuyHoldingNote({
  item,
  currentQty,
}: {
  item: RebalancingItem;
  currentQty: number;
}) {
  if (item.target_qty != null) {
    return (
      <>
        {currentQty > 0 ? `${currentQty.toLocaleString()}주` : "미보유"} → 목표{" "}
        {item.target_qty.toFixed(0)}주
      </>
    );
  }
  return <>{currentQty > 0 ? `현재 ${currentQty.toLocaleString()}주 보유` : "현재 미보유"}</>;
}

/** 분할 매수 배분 현황 — 다 배분하지 않았으면 주황 */
export function AllocationNote({ allocated, needed }: { allocated: number; needed: number }) {
  return (
    <div
      className={`text-xs mt-0.5 text-right ${
        allocated === needed
          ? "text-gray-500 dark:text-gray-500"
          : "text-amber-600 dark:text-amber-400"
      }`}
    >
      배분 {allocated} / {needed}주
    </div>
  );
}

export function PriceErrorBanner({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="mx-3 mb-2 px-3 py-2 flex items-center justify-between gap-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 border border-amber-200 dark:bg-amber-950/30 dark:border-amber-700/40 rounded-lg"
    >
      <span>현재가 조회 실패 — 지정가를 직접 입력하거나 다시 시도하세요.</span>
      <button
        onClick={onRetry}
        className="shrink-0 flex items-center gap-1 px-2 py-1 rounded bg-amber-200 dark:bg-amber-800/40 hover:bg-amber-300 dark:hover:bg-amber-800/60 text-amber-800 dark:text-amber-200 transition-colors"
      >
        <RefreshCw size={12} />
        재조회
      </button>
    </div>
  );
}

export function QtyInput({
  value,
  max,
  colorClass,
  onChange,
}: {
  value: number;
  max?: number;
  colorClass: string;
  onChange: (qty: number) => void;
}) {
  return (
    <div className="flex items-center justify-end gap-1">
      <input
        type="number"
        inputMode="numeric"
        min={0}
        max={max}
        value={value || ""}
        onFocus={(e) => e.target.select()}
        onChange={(e) => onChange(parseInt(e.target.value) || 0)}
        className={`w-16 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded px-2 py-0.5 text-right ${colorClass} font-medium focus:outline-none focus:border-indigo-500`}
      />
      <span className="text-gray-500 dark:text-gray-400">주</span>
    </div>
  );
}

/** 데스크톱 주문표 한 행 — 매도·매수 공용(행 클릭=선택 토글, 입력 칸 클릭은 전파 차단) */
export function DesktopOrderRow({
  item,
  row,
  isBuy,
  note,
  selected,
  orderType,
  priceState,
  livePricesKrw,
  livePricesUsd,
  priceRetrying,
  onRetryPrice,
  globalUsdRate,
  dispatch,
  qtyInput,
  qtyFooter,
  trailing,
}: {
  item: RebalancingItem;
  row: OrderRowModel;
  isBuy: boolean;
  note: React.ReactNode;
  selected: boolean;
  orderType: OrderType;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  priceRetrying: Set<string>;
  onRetryPrice: (ticker: string, market: string) => void;
  globalUsdRate: number | null;
  dispatch: React.Dispatch<ExecutionAction>;
  qtyInput: React.ReactNode;
  qtyFooter: React.ReactNode;
  trailing: React.ReactNode;
}) {
  const toggle = () => dispatch({ type: "TOGGLE_SELECTED", key: row.key });
  return (
    <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/40 cursor-pointer" onClick={toggle}>
      <td className="px-3 py-2">
        <input
          type="checkbox"
          checked={selected}
          onChange={toggle}
          onClick={(e) => e.stopPropagation()}
          className="accent-indigo-500"
        />
      </td>
      <td className="px-3 py-2">
        <div className="text-gray-900 dark:text-white font-medium truncate">{item.name}</div>
        <div className="text-gray-500 dark:text-gray-400 text-xs">{item.ticker}</div>
        <div className="text-gray-500 dark:text-gray-500 text-xs">{note}</div>
      </td>
      <td className="px-3 py-2 text-center">
        <SideBadge isBuy={isBuy} />
      </td>
      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
        <PriceCell
          ticker={item.ticker}
          market={item.market}
          priceState={priceState}
          livePricesKrw={livePricesKrw}
          livePricesUsd={livePricesUsd}
          priceRetrying={priceRetrying}
          onRetryPrice={onRetryPrice}
        />
      </td>
      <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
        {qtyInput}
        {qtyFooter}
      </td>
      <RebalancingPriceInput
        orderKey={row.key}
        market={item.market}
        qty={row.qty}
        orderType={orderType}
        priceState={priceState}
        nativeVal={row.nativeLimitPrice}
        currentNativePrice={row.currentNativePrice}
        globalUsdRate={globalUsdRate}
        dispatch={dispatch}
      />
      {trailing}
    </tr>
  );
}
