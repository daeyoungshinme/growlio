import React from "react";
import type { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { SideBadge } from "./RebalancingBadges";
import { isOverseasMarket } from "@/hooks/useRebalancingExecution";
import type { ExecutionAction, OrderType, PriceLoadState } from "@/hooks/useRebalancingExecution";
import { PriceCell } from "./RebalancingPriceCell";

export interface RebalancingMobileCardProps {
  orderKey: string;
  item: RebalancingItem;
  qty: number;
  isBuy: boolean;
  extra?: React.ReactNode;
  selected: Set<string>;
  orderType: OrderType;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  globalUsdRate: number | null;
  nativeLimitPrice: number;
  currentNativePrice: number | undefined;
  estKrw: number;
  marketOrderEst: number | null;
  dispatch: React.Dispatch<ExecutionAction>;
}

export function RebalancingMobileCard({
  orderKey,
  item,
  qty,
  isBuy,
  extra,
  selected,
  orderType,
  priceState,
  livePricesKrw,
  livePricesUsd,
  globalUsdRate,
  nativeLimitPrice,
  currentNativePrice,
  estKrw,
  marketOrderEst,
  dispatch,
}: RebalancingMobileCardProps) {
  const overseas = isOverseasMarket(item.market);

  return (
    <div className={`px-3 py-1.5 ${selected.has(orderKey) ? "bg-indigo-950/20" : ""}`}>
      {/* Row 1: checkbox | 종목명+티커 | qty input */}
      <div className="flex items-start gap-2">
        <input
          type="checkbox"
          checked={selected.has(orderKey)}
          onChange={() => dispatch({ type: "TOGGLE_SELECTED", key: orderKey })}
          className="mt-0.5 w-5 h-5 accent-indigo-500 shrink-0"
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium text-white text-sm">{item.name}</span>
            <SideBadge isBuy={isBuy} />
          </div>
          <p className="text-gray-400 text-xs">{item.ticker}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="flex items-center gap-1">
            <input
              type="number"
              min={0}
              value={qty || ""}
              onFocus={(e) => e.target.select()}
              onChange={(e) =>
                dispatch({
                  type: isBuy ? "SET_QTY_AND_SELECT" : "SET_QTY",
                  key: orderKey,
                  qty: parseInt(e.target.value) || 0,
                })
              }
              className={`w-24 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-right font-medium text-sm focus:outline-none focus:border-indigo-500 ${
                isBuy ? "text-red-400" : "text-blue-400"
              }`}
            />
            <span className="text-gray-400 text-sm shrink-0">주</span>
          </div>
          {marketOrderEst != null && orderType === "MARKET" && (
            <p className="text-[11px] text-gray-500 mt-0.5">≈ {fmtKrw(marketOrderEst)}</p>
          )}
          {extra}
        </div>
      </div>

      {/* Row 2: 현재가 인라인 */}
      <div className="mt-0.5 pl-7 flex items-center gap-1.5">
        <span className="text-[11px] text-gray-500">현재가</span>
        <PriceCell
          ticker={item.ticker}
          market={item.market}
          large
          priceState={priceState}
          livePricesKrw={livePricesKrw}
          livePricesUsd={livePricesUsd}
        />
      </div>

      {orderType === "LIMIT" && (
        <div className="mt-1 pl-7">
          <div className="flex items-center justify-between mb-0.5">
            <p className="text-[11px] text-gray-500">지정가</p>
            {priceState === "loaded" && currentNativePrice != null && (
              <button
                onClick={() =>
                  dispatch({ type: "SET_LIMIT_PRICE", key: orderKey, price: currentNativePrice })
                }
                className="text-[11px] text-indigo-400 hover:text-indigo-300"
              >
                현재가로
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="number"
              min={0}
              step={overseas ? 0.01 : 1}
              value={nativeLimitPrice || ""}
              placeholder={overseas ? "USD 입력" : "원 입력"}
              onChange={(e) =>
                dispatch({
                  type: "SET_LIMIT_PRICE",
                  key: orderKey,
                  price: parseFloat(e.target.value) || 0,
                })
              }
              className="flex-1 bg-gray-800 border border-indigo-600/50 rounded px-2 py-1 text-right text-indigo-300 font-medium text-sm focus:outline-none focus:border-indigo-500"
            />
            <span className="text-gray-400 text-sm shrink-0">{overseas ? "USD" : "원"}</span>
          </div>
          {nativeLimitPrice > 0 && (
            <p className="text-[11px] text-gray-600 mt-0.5 text-right">
              ≈{" "}
              {fmtKrw(
                overseas && globalUsdRate != null ? nativeLimitPrice * globalUsdRate : nativeLimitPrice
              )}{" "}
              × {qty}주 = {fmtKrw(estKrw)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
