import React from "react";
import { fmtKrw } from "@/utils/format";
import { isOverseasMarket } from "@/constants/markets";
import { estimateLimitKrw, limitPriceKrw } from "./rebalancingTradeMath";
import type { ExecutionAction, OrderType, PriceLoadState } from "@/hooks/useRebalancingExecution";

export interface RebalancingPriceInputProps {
  orderKey: string;
  market: string;
  qty: number;
  orderType: OrderType;
  priceState: PriceLoadState;
  nativeVal: number;
  currentNativePrice: number | undefined;
  globalUsdRate: number | null;
  dispatch: React.Dispatch<ExecutionAction>;
}

export function RebalancingPriceInput({
  orderKey,
  market,
  qty,
  orderType,
  priceState,
  nativeVal,
  currentNativePrice,
  globalUsdRate,
  dispatch,
}: RebalancingPriceInputProps) {
  // 지정가 열(헤더·colgroup)은 LIMIT일 때만 있다 — 빈 칸을 내면 시장가 행이 헤더보다 한 칸 많아진다
  if (orderType !== "LIMIT") return null;
  const overseas = isOverseasMarket(market);
  const estKrw = estimateLimitKrw(nativeVal, qty, market, globalUsdRate);
  return (
    <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-end gap-1">
        <input
          type="number"
          inputMode="decimal"
          min={0}
          step={overseas ? 0.01 : 1}
          value={nativeVal || ""}
          placeholder={overseas ? "USD" : "KRW"}
          onChange={(e) =>
            dispatch({
              type: "SET_LIMIT_PRICE",
              key: orderKey,
              price: parseFloat(e.target.value) || 0,
            })
          }
          className="w-24 bg-white dark:bg-gray-800 border border-indigo-300 dark:border-indigo-600/50 rounded px-2 py-0.5 text-right text-indigo-700 dark:text-indigo-300 font-medium text-xs focus:outline-none focus:border-indigo-500"
        />
        <span className="text-gray-500 text-xs">{overseas ? "USD" : "원"}</span>
      </div>
      {!overseas && (
        // 백엔드가 주문 직전에 호가 격자로 맞춘다(services/rebalancing/krx_tick.py, plans/61 C2)
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          호가단위로 보정(매수 내림·매도 올림)
        </p>
      )}
      {priceState === "loaded" && currentNativePrice != null && (
        <button
          onClick={() =>
            dispatch({ type: "SET_LIMIT_PRICE", key: orderKey, price: currentNativePrice })
          }
          className="text-xs text-indigo-600 dark:text-indigo-400 hover:text-indigo-500 dark:hover:text-indigo-300 mt-0.5 block ml-auto"
        >
          현재가로
        </button>
      )}
      {nativeVal > 0 && (
        <div className="text-xs text-gray-500 dark:text-gray-600 mt-0.5 text-right leading-tight">
          <div>
            ≈ {fmtKrw(limitPriceKrw(nativeVal, market, globalUsdRate))} × {qty}주
          </div>
          <div>= {fmtKrw(estKrw)}</div>
        </div>
      )}
    </td>
  );
}
