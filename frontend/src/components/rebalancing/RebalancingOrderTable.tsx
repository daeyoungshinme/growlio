import React from "react";
import type { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw, fmtKrwPrice } from "@/utils/format";
import { SideBadge } from "./RebalancingBadges";
import type { ExecutionAction, OrderType, PriceLoadState } from "@/hooks/useRebalancingExecution";
import { isOverseasMarket } from "@/hooks/useRebalancingExecution";

// ─── PriceCell ────────────────────────────────────────────────────────────────

interface PriceCellProps {
  ticker: string;
  market: string;
  large?: boolean;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
}

export function PriceCell({ ticker, market, large, priceState, livePricesKrw, livePricesUsd }: PriceCellProps) {
  const krw = livePricesKrw[ticker];
  const usd = livePricesUsd[ticker];
  const priceCls = large ? "text-sm" : "text-[11px]";
  if (priceState === "loading") return <span className="text-gray-600 text-[11px]">조회 중</span>;
  if (krw != null) {
    if (isOverseasMarket(market) && usd != null) {
      return (
        <div>
          <div className={`text-gray-300 ${priceCls}`}>${usd.toFixed(2)}</div>
          <div className="text-gray-500 text-[11px]">≈ {fmtKrwPrice(krw)}</div>
        </div>
      );
    }
    return <span className={`text-gray-300 ${priceCls}`}>{fmtKrwPrice(krw)}</span>;
  }
  return <span className={`text-gray-600 ${priceCls}`}>—</span>;
}

// ─── RebalancingPriceInput ────────────────────────────────────────────────────

interface RebalancingPriceInputProps {
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

// ─── RebalancingMobileCard ────────────────────────────────────────────────────

interface RebalancingMobileCardProps {
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

function RebalancingMobileCard({
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

// ─── RebalancingOrderTable ────────────────────────────────────────────────────

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
    <>
      {/* 모바일 카드 뷰 */}
      <div className="md:hidden divide-y divide-gray-700/30">
        {sellRows.length > 0 && (
          <>
            <div className="px-3 py-1.5 text-[11px] text-gray-500 bg-gray-800/30">매도</div>
            {sellRows.map(({ item, currentQty, suggestedQty }) => {
              const key = `sell_${item.ticker}_${accId}`;
              const qty = qtyOverrides[key] ?? suggestedQty;
              const overseas = isOverseasMarket(item.market);
              const nativeLimitPrice = getLimitPriceNative(key, item.ticker, item.market);
              const currentNativePrice = overseas ? livePricesUsd[item.ticker] : livePricesKrw[item.ticker];
              const est = getEstimateKrw(key, item.ticker, item.market, qty);
              const estKrw =
                overseas && globalUsdRate != null
                  ? nativeLimitPrice * globalUsdRate * qty
                  : nativeLimitPrice * qty;
              return (
                <RebalancingMobileCard
                  key={key}
                  orderKey={key}
                  item={item}
                  qty={qty}
                  isBuy={false}
                  extra={
                    <p className="text-[11px] text-gray-500 mt-0.5 text-right">
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
            <div className="px-3 py-1.5 text-[11px] text-gray-500 bg-gray-800/30">매수</div>
            {buyRows.map(({ item, suggestedQty, currentQty }) => {
              const key = `buy_${item.ticker}_${accId}`;
              const qty = qtyOverrides[key] ?? suggestedQty;
              const isMultiAccount = (buyAccounts[item.ticker] ?? []).length > 1;
              const { allocated, needed } = isMultiAccount
                ? getBuyTotalInfo(item.ticker)
                : { allocated: 0, needed: 0 };
              const overseas = isOverseasMarket(item.market);
              const nativeLimitPrice = getLimitPriceNative(key, item.ticker, item.market);
              const currentNativePrice = overseas ? livePricesUsd[item.ticker] : livePricesKrw[item.ticker];
              const est = getEstimateKrw(key, item.ticker, item.market, qty);
              const estKrw =
                overseas && globalUsdRate != null
                  ? nativeLimitPrice * globalUsdRate * qty
                  : nativeLimitPrice * qty;
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
                        className={`text-[11px] mt-0.5 text-right ${
                          allocated === needed ? "text-gray-500" : "text-amber-400"
                        }`}
                      >
                        배분 {allocated} / {needed}주
                      </div>
                    ) : (
                      <p className="text-[11px] text-gray-500 mt-0.5 text-right">
                        {currentQty > 0
                          ? `현재 ${currentQty.toLocaleString()}주 보유`
                          : "현재 미보유"}
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
            <tr className="text-[11px] text-gray-500 border-b border-gray-700/50">
              <th />
              <th className="px-3 py-2 text-left font-normal">종목</th>
              <th className="px-3 py-2 text-center font-normal">구분</th>
              <th className="px-2 py-2 text-right font-normal">현재가</th>
              <th className="px-3 py-2 text-right font-normal">수량</th>
              {orderType === "LIMIT" && (
                <th className="px-2 py-2 text-right font-normal">지정가</th>
              )}
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700/30">
            {sellRows.length > 0 && (
              <>
                <tr>
                  <td
                    colSpan={orderType === "LIMIT" ? 7 : 6}
                    className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30"
                  >
                    매도
                  </td>
                </tr>
                {sellRows.map(({ item, currentQty, suggestedQty }) => {
                  const key = `sell_${item.ticker}_${accId}`;
                  const qty = qtyOverrides[key] ?? suggestedQty;
                  const est = getEstimateKrw(key, item.ticker, item.market, qty);
                  const nativeVal = getLimitPriceNative(key, item.ticker, item.market);
                  const overseas = isOverseasMarket(item.market);
                  const currentNativePrice = overseas
                    ? livePricesUsd[item.ticker]
                    : livePricesKrw[item.ticker];
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
                        <div className="text-gray-400 text-[11px]">{item.ticker}</div>
                        <div className="text-gray-500 text-[11px]">
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
                          <div className="text-[11px] text-gray-500 mt-0.5 text-right">
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
                    className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30"
                  >
                    매수
                  </td>
                </tr>
                {buyRows.map(({ item, suggestedQty, currentQty }) => {
                  const key = `buy_${item.ticker}_${accId}`;
                  const qty = qtyOverrides[key] ?? suggestedQty;
                  const est = getEstimateKrw(key, item.ticker, item.market, qty);
                  const nativeVal = getLimitPriceNative(key, item.ticker, item.market);
                  const overseas = isOverseasMarket(item.market);
                  const currentNativePrice = overseas
                    ? livePricesUsd[item.ticker]
                    : livePricesKrw[item.ticker];
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
                        <div className="text-gray-400 text-[11px]">{item.ticker}</div>
                        <div className="text-gray-500 text-[11px]">
                          {currentQty > 0
                            ? `현재 ${currentQty.toLocaleString()}주 보유`
                            : "현재 미보유"}
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
                            className={`text-[11px] mt-0.5 text-right ${
                              allocated === needed ? "text-gray-500" : "text-amber-400"
                            }`}
                          >
                            배분 {allocated} / {needed}주
                          </div>
                        ) : (
                          est != null &&
                          orderType === "MARKET" && (
                            <div className="text-[11px] text-gray-500 mt-0.5 text-right">
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
    </>
  );
}
