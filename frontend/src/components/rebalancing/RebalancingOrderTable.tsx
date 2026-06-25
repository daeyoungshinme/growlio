import React from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import { SideBadge } from "./RebalancingBadges";
import type { ExecutionAction, OrderType, PriceLoadState } from "@/hooks/useRebalancingExecution";
import { isOverseasMarket } from "@/hooks/useRebalancingExecution";
import { PriceCell } from "./RebalancingPriceCell";
import { RebalancingPriceInput } from "./RebalancingPriceInput";
import { RebalancingMobileCard } from "./RebalancingMobileCard";

export type { PriceCellProps } from "./RebalancingPriceCell";
export { PriceCell } from "./RebalancingPriceCell";
export { RebalancingPriceInput } from "./RebalancingPriceInput";

function getNativePrice(
  ticker: string,
  market: string,
  livePricesKrw: Record<string, number>,
  livePricesUsd: Record<string, number>,
): number | undefined {
  return isOverseasMarket(market) ? livePricesUsd[ticker] : livePricesKrw[ticker];
}

function getLimitEstKrw(
  nativeLimitPrice: number,
  qty: number,
  market: string,
  globalUsdRate: number | null,
): number {
  return isOverseasMarket(market) && globalUsdRate != null
    ? nativeLimitPrice * globalUsdRate * qty
    : nativeLimitPrice * qty;
}

export interface RebalancingOrderTableProps {
  accId: string;
  sellRows: { item: RebalancingItem; currentQty: number; suggestedQty: number }[];
  buyRows: { item: RebalancingItem; suggestedQty: number; currentQty: number }[];
  orderType: OrderType;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  globalUsdRate: number | null;
  selected: Set<string>;
  qtyOverrides: Record<string, number>;
  buyAccounts: Record<string, string[]>;
  dispatch: React.Dispatch<ExecutionAction>;
  getLimitPriceNative: (key: string, ticker: string, market: string) => number;
  getEstimateKrw: (key: string, ticker: string, market: string, qty: number) => number | null;
  getBuyTotalInfo: (ticker: string) => { allocated: number; needed: number };
}

export function RebalancingOrderTable({
  accId,
  sellRows,
  buyRows,
  orderType,
  priceState,
  livePricesKrw,
  livePricesUsd,
  globalUsdRate,
  selected,
  qtyOverrides,
  buyAccounts,
  dispatch,
  getLimitPriceNative,
  getEstimateKrw,
  getBuyTotalInfo,
}: RebalancingOrderTableProps) {
  return (
    <ErrorBoundary variant="section">
      {priceState === "error" && (
        <div
          role="alert"
          className="mx-3 mb-2 px-3 py-2 text-xs text-amber-400 bg-amber-950/30 border border-amber-700/40 rounded-lg"
        >
          현재가 조회 실패 — 지정가를 직접 입력하거나 잠시 후 다시 시도하세요.
        </div>
      )}
      {/* 모바일 카드 뷰 */}
      <div className="md:hidden divide-y divide-gray-700/30">
        {sellRows.length > 0 && (
          <>
            <div className="px-3 py-1.5 text-xs text-gray-500 bg-gray-800/30">매도</div>
            {sellRows.map(({ item, currentQty, suggestedQty }) => {
              const key = `sell_${item.ticker}_${accId}`;
              const qty = qtyOverrides[key] ?? suggestedQty;
              const nativeLimitPrice = getLimitPriceNative(key, item.ticker, item.market);
              const currentNativePrice = getNativePrice(
                item.ticker,
                item.market,
                livePricesKrw,
                livePricesUsd,
              );
              const est = getEstimateKrw(key, item.ticker, item.market, qty);
              const estKrw = getLimitEstKrw(nativeLimitPrice, qty, item.market, globalUsdRate);
              return (
                <RebalancingMobileCard
                  key={key}
                  orderKey={key}
                  item={item}
                  qty={qty}
                  isBuy={false}
                  maxQty={currentQty}
                  extra={
                    <p className="text-xs text-gray-500 mt-0.5 text-right">
                      현재 {currentQty.toLocaleString()}주 보유
                    </p>
                  }
                  selected={selected}
                  orderType={orderType}
                  priceState={priceState}
                  livePricesKrw={livePricesKrw}
                  livePricesUsd={livePricesUsd}
                  globalUsdRate={globalUsdRate}
                  nativeLimitPrice={nativeLimitPrice}
                  currentNativePrice={currentNativePrice}
                  estKrw={estKrw}
                  marketOrderEst={est}
                  dispatch={dispatch}
                />
              );
            })}
          </>
        )}
        {buyRows.length > 0 && (
          <>
            <div className="px-3 py-1.5 text-xs text-gray-500 bg-gray-800/30">매수</div>
            {buyRows.map(({ item, suggestedQty, currentQty }) => {
              const key = `buy_${item.ticker}_${accId}`;
              const qty = qtyOverrides[key] ?? suggestedQty;
              const isMultiAccount = (buyAccounts[item.ticker] ?? []).length > 1;
              const { allocated, needed } = isMultiAccount
                ? getBuyTotalInfo(item.ticker)
                : { allocated: 0, needed: 0 };
              const nativeLimitPrice = getLimitPriceNative(key, item.ticker, item.market);
              const currentNativePrice = getNativePrice(
                item.ticker,
                item.market,
                livePricesKrw,
                livePricesUsd,
              );
              const est = getEstimateKrw(key, item.ticker, item.market, qty);
              const estKrw = getLimitEstKrw(nativeLimitPrice, qty, item.market, globalUsdRate);
              return (
                <RebalancingMobileCard
                  key={key}
                  orderKey={key}
                  item={item}
                  qty={qty}
                  isBuy={true}
                  extra={
                    isMultiAccount ? (
                      <div
                        className={`text-xs mt-0.5 text-right ${
                          allocated === needed ? "text-gray-500" : "text-amber-400"
                        }`}
                      >
                        배분 {allocated} / {needed}주
                      </div>
                    ) : (
                      <p className="text-xs text-gray-500 mt-0.5 text-right">
                        {item.target_qty != null ? (
                          <>
                            {currentQty > 0 ? `${currentQty.toLocaleString()}주` : "미보유"} → 목표{" "}
                            {item.target_qty.toFixed(0)}주
                          </>
                        ) : currentQty > 0 ? (
                          `현재 ${currentQty.toLocaleString()}주 보유`
                        ) : (
                          "현재 미보유"
                        )}
                      </p>
                    )
                  }
                  selected={selected}
                  orderType={orderType}
                  priceState={priceState}
                  livePricesKrw={livePricesKrw}
                  livePricesUsd={livePricesUsd}
                  globalUsdRate={globalUsdRate}
                  nativeLimitPrice={nativeLimitPrice}
                  currentNativePrice={currentNativePrice}
                  estKrw={estKrw}
                  marketOrderEst={est}
                  dispatch={dispatch}
                />
              );
            })}
          </>
        )}
      </div>

      {/* 데스크탑 테이블 */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-xs">
          <colgroup>
            <col style={{ width: "32px" }} />
            <col />
            <col style={{ width: "56px" }} />
            <col style={{ width: "125px" }} />
            <col style={{ width: "140px" }} />
            {orderType === "LIMIT" && <col style={{ width: "190px" }} />}
            <col style={{ width: "32px" }} />
          </colgroup>
          <thead>
            <tr className="text-xs text-gray-500 border-b border-gray-700/50">
              <th scope="col" />
              <th scope="col" className="px-3 py-2 text-left font-normal">
                종목
              </th>
              <th scope="col" className="px-3 py-2 text-center font-normal">
                구분
              </th>
              <th scope="col" className="px-2 py-2 text-right font-normal">
                현재가
              </th>
              <th scope="col" className="px-3 py-2 text-right font-normal">
                수량
              </th>
              {orderType === "LIMIT" && (
                <th scope="col" className="px-2 py-2 text-right font-normal">
                  지정가
                </th>
              )}
              <th scope="col" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700/30">
            {sellRows.length > 0 && (
              <>
                <tr>
                  <td
                    colSpan={orderType === "LIMIT" ? 7 : 6}
                    className="px-4 py-1.5 text-xs text-gray-500 bg-gray-800/30"
                  >
                    매도
                  </td>
                </tr>
                {sellRows.map(({ item, currentQty, suggestedQty }) => {
                  const key = `sell_${item.ticker}_${accId}`;
                  const qty = qtyOverrides[key] ?? suggestedQty;
                  const est = getEstimateKrw(key, item.ticker, item.market, qty);
                  const nativeVal = getLimitPriceNative(key, item.ticker, item.market);
                  const currentNativePrice = getNativePrice(
                    item.ticker,
                    item.market,
                    livePricesKrw,
                    livePricesUsd,
                  );
                  return (
                    <tr
                      key={key}
                      className="hover:bg-gray-800/40 cursor-pointer"
                      onClick={() => dispatch({ type: "TOGGLE_SELECTED", key })}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selected.has(key)}
                          onChange={() => dispatch({ type: "TOGGLE_SELECTED", key })}
                          onClick={(e) => e.stopPropagation()}
                          className="accent-indigo-500"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <div className="text-white font-medium truncate">{item.name}</div>
                        <div className="text-gray-400 text-xs">{item.ticker}</div>
                        <div className="text-gray-500 text-xs">
                          현재 {currentQty.toLocaleString()}주 보유
                        </div>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <SideBadge isBuy={false} />
                      </td>
                      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <PriceCell
                          ticker={item.ticker}
                          market={item.market}
                          priceState={priceState}
                          livePricesKrw={livePricesKrw}
                          livePricesUsd={livePricesUsd}
                        />
                      </td>
                      <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          <input
                            type="number"
                            min={0}
                            max={currentQty}
                            value={qty || ""}
                            onFocus={(e) => e.target.select()}
                            onChange={(e) =>
                              dispatch({
                                type: "SET_QTY",
                                key,
                                qty: parseInt(e.target.value) || 0,
                              })
                            }
                            className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-blue-400 font-medium focus:outline-none focus:border-indigo-500"
                          />
                          <span className="text-gray-400">주</span>
                        </div>
                        {est != null && orderType === "MARKET" && (
                          <div className="text-xs text-gray-500 mt-0.5 text-right">
                            ≈ {fmtKrw(est)}
                          </div>
                        )}
                      </td>
                      <RebalancingPriceInput
                        orderKey={key}
                        market={item.market}
                        qty={qty}
                        orderType={orderType}
                        priceState={priceState}
                        nativeVal={nativeVal}
                        currentNativePrice={currentNativePrice}
                        globalUsdRate={globalUsdRate}
                        dispatch={dispatch}
                      />
                      <td />
                    </tr>
                  );
                })}
              </>
            )}

            {buyRows.length > 0 && (
              <>
                <tr>
                  <td
                    colSpan={orderType === "LIMIT" ? 7 : 6}
                    className="px-4 py-1.5 text-xs text-gray-500 bg-gray-800/30"
                  >
                    매수
                  </td>
                </tr>
                {buyRows.map(({ item, suggestedQty, currentQty }) => {
                  const key = `buy_${item.ticker}_${accId}`;
                  const qty = qtyOverrides[key] ?? suggestedQty;
                  const est = getEstimateKrw(key, item.ticker, item.market, qty);
                  const nativeVal = getLimitPriceNative(key, item.ticker, item.market);
                  const currentNativePrice = getNativePrice(
                    item.ticker,
                    item.market,
                    livePricesKrw,
                    livePricesUsd,
                  );
                  const isMultiAccount = (buyAccounts[item.ticker] ?? []).length > 1;
                  const isOnlyAccount = !isMultiAccount;
                  const { allocated, needed } = isMultiAccount
                    ? getBuyTotalInfo(item.ticker)
                    : { allocated: 0, needed: 0 };
                  return (
                    <tr
                      key={key}
                      className="hover:bg-gray-800/40 cursor-pointer"
                      onClick={() => dispatch({ type: "TOGGLE_SELECTED", key })}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={selected.has(key)}
                          onChange={() => dispatch({ type: "TOGGLE_SELECTED", key })}
                          onClick={(e) => e.stopPropagation()}
                          className="accent-indigo-500"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <div className="text-white font-medium truncate">{item.name}</div>
                        <div className="text-gray-400 text-xs">{item.ticker}</div>
                        <div className="text-gray-500 text-xs">
                          {item.target_qty != null ? (
                            <>
                              {currentQty > 0
                                ? `${currentQty.toLocaleString()}주`
                                : "미보유"}{" "}
                              → 목표 {item.target_qty.toFixed(0)}주
                            </>
                          ) : currentQty > 0 ? (
                            `현재 ${currentQty.toLocaleString()}주 보유`
                          ) : (
                            "현재 미보유"
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <SideBadge isBuy={true} />
                      </td>
                      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <PriceCell
                          ticker={item.ticker}
                          market={item.market}
                          priceState={priceState}
                          livePricesKrw={livePricesKrw}
                          livePricesUsd={livePricesUsd}
                        />
                      </td>
                      <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          <input
                            type="number"
                            min={0}
                            value={qty || ""}
                            onFocus={(e) => e.target.select()}
                            onChange={(e) =>
                              dispatch({
                                type: "SET_QTY_AND_SELECT",
                                key,
                                qty: parseInt(e.target.value) || 0,
                              })
                            }
                            className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-red-400 font-medium focus:outline-none focus:border-indigo-500"
                          />
                          <span className="text-gray-400">주</span>
                        </div>
                        {isMultiAccount ? (
                          <div
                            className={`text-xs mt-0.5 text-right ${
                              allocated === needed ? "text-gray-500" : "text-amber-400"
                            }`}
                          >
                            배분 {allocated} / {needed}주
                          </div>
                        ) : (
                          est != null &&
                          orderType === "MARKET" && (
                            <div className="text-xs text-gray-500 mt-0.5 text-right">
                              ≈ {fmtKrw(est)}
                            </div>
                          )
                        )}
                      </td>
                      <RebalancingPriceInput
                        orderKey={key}
                        market={item.market}
                        qty={qty}
                        orderType={orderType}
                        priceState={priceState}
                        nativeVal={nativeVal}
                        currentNativePrice={currentNativePrice}
                        globalUsdRate={globalUsdRate}
                        dispatch={dispatch}
                      />
                      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() =>
                            dispatch({
                              type: "REMOVE_BUY_ACCOUNT",
                              ticker: item.ticker,
                              accountId: accId,
                            })
                          }
                          disabled={isOnlyAccount}
                          title="이 계좌에서 제거"
                          aria-label="이 계좌에서 제거"
                          className="text-gray-600 hover:text-red-400 disabled:opacity-20 disabled:cursor-not-allowed transition-colors text-sm leading-none px-1"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </>
            )}
          </tbody>
        </table>
      </div>
    </ErrorBoundary>
  );
}
