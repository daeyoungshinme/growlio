import React from "react";
import { fmtKrw } from "@/utils/format";
import { isOverseasMarket } from "@/hooks/useRebalancingExecution";
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
  if (orderType !== "LIMIT") return <td />;
  const overseas = isOverseasMarket(market);
  const estKrw =
    overseas && globalUsdRate != null ? nativeVal * globalUsdRate * qty : nativeVal * qty;
  return (
    <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center justify-end gap-1">
        <input
          type="number"
          min={0}
          step={overseas ? 0.01 : 1}
          value={nativeVal || ""}
          placeholder={overseas ? "USD" : "KRW"}
          onChange={(e) =>
            dispatch({ type: "SET_LIMIT_PRICE", key: orderKey, price: parseFloat(e.target.value) || 0 })
          }
          className="w-20 bg-gray-800 border border-indigo-600/50 rounded px-2 py-0.5 text-right text-indigo-300 font-medium text-[11px] focus:outline-none focus:border-indigo-500"
        />
        <span className="text-gray-500 text-[11px]">{overseas ? "USD" : "원"}</span>
      </div>
      {priceState === "loaded" && currentNativePrice != null && (
        <button
          onClick={() => dispatch({ type: "SET_LIMIT_PRICE", key: orderKey, price: currentNativePrice })}
          className="text-[10px] text-indigo-400 hover:text-indigo-300 mt-0.5 block ml-auto"
        >
          현재가로
        </button>
      )}
      {nativeVal > 0 && (
        <div className="text-[11px] text-gray-600 mt-0.5 text-right leading-tight">
          <div>
            ≈ {fmtKrw(overseas && globalUsdRate != null ? nativeVal * globalUsdRate : nativeVal)} ×{" "}
            {qty}주
          </div>
          <div>= {fmtKrw(estKrw)}</div>
        </div>
      )}
    </td>
  );
}
