import React from "react";
import { RebalancingItem } from "../../api/rebalancing";
import { fmtKrw, fmtKrwPrice } from "../../utils/format";
import { SideBadge } from "./RebalancingBadges";
import { CashAnalysis, ExecutionAction, OrderType, PriceLoadState, isOverseasMarket, useRebalancingExecutionContext } from "../../hooks/useRebalancingExecution";

// ─── 하위 컴포넌트 ─────────────────────────────────────────────────────────────

interface PriceCellProps {
  ticker: string;
  market: string;
  large?: boolean;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
}

function PriceCell({ ticker, market, large, priceState, livePricesKrw, livePricesUsd }: PriceCellProps) {
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

function RebalancingPriceInput({
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

interface RebalancingOrderTableProps {
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

function RebalancingOrderTable({
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

function CashSummaryBar({ analysis }: { analysis: CashAnalysis }) {
  const { deposit, isOrderableKnown, sellProceeds, totalAvailable, buyCost, surplus } = analysis;
  if (deposit === null) return null;
  const hasSell = sellProceeds !== null && sellProceeds > 0;
  const hasBuy = buyCost !== null && buyCost > 0;
  const surplusKnown = surplus !== null;
  return (
    <div className="px-4 py-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] bg-gray-900/20 border-b border-gray-700/30">
      <span className="text-gray-500">
        {isOrderableKnown ? "주문가능" : "예수금"}{" "}
        <span className="text-gray-300">{fmtKrwPrice(deposit)}</span>
        {!isOrderableKnown && (
          <span className="text-gray-600 ml-1">(미체결 주문 시 차이 발생)</span>
        )}
      </span>
      {hasSell && (
        <span className="text-gray-500">
          + 매도예상 <span className="text-blue-400">+{fmtKrwPrice(sellProceeds!)}</span>
        </span>
      )}
      {hasSell && totalAvailable !== null && (
        <span className="text-gray-500">
          = 사용가능 <span className="text-gray-200">{fmtKrwPrice(totalAvailable)}</span>
        </span>
      )}
      {hasBuy && <span className="text-gray-600">|</span>}
      {hasBuy && (
        <span className="text-gray-500">
          매수필요 <span className="text-red-400">{fmtKrwPrice(buyCost!)}</span>
        </span>
      )}
      {surplusKnown && hasBuy && (
        <span className={surplus! >= 0 ? "text-green-400" : "text-amber-400"}>
          {surplus! >= 0 ? `여유 +${fmtKrwPrice(surplus!)}` : `부족 ${fmtKrwPrice(Math.abs(surplus!))}`}
        </span>
      )}
    </div>
  );
}

// ─── 메인 컴포넌트 ──────────────────────────────────────────────────────────────

interface Props {
  ordersCount: number;
}

export function RebalancingConfirmStep({ ordersCount }: Props) {
  const exec = useRebalancingExecutionContext();
  const {
    kisAccounts,
    actionableItems,
    state,
    dispatch,
    getSellRows,
    getBuyRows,
    getBuyTotalInfo,
    getAccountSummary,
    getLimitPriceNative,
    getEstimateKrw,
    loadLiveBalance,
    hasRealAccount,
  } = exec;
  const {
    balanceState,
    depositKrw,
    priceState,
    priceLoadProgress,
    livePricesKrw,
    livePricesUsd,
    globalUsdRate,
    orderType,
    qtyOverrides,
    selected,
    buyAccounts,
    errorMsg,
    confirmed,
  } = state;

  return (
    <>
      <div className="rounded-lg bg-yellow-900/30 border border-yellow-700/50 px-4 py-3 text-xs text-yellow-300">
        주문이 즉시 체결됩니다. 내용을 신중히 확인하세요.
      </div>

      {hasRealAccount && (
        <div className="rounded-lg bg-red-900/30 border border-red-700/50 px-4 py-3 text-xs text-red-300 font-medium">
          실계좌 주문입니다. 실제 자금이 사용됩니다.
        </div>
      )}

      <div className="text-xs text-gray-500">
        시장이 닫혀 있을 경우 주문이 예약될 수 있습니다.
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-gray-400">주문 유형</span>
        <div className="flex rounded-lg border border-gray-700 overflow-hidden">
          {(["MARKET", "LIMIT"] as OrderType[]).map((type) => (
            <button
              key={type}
              onClick={() => dispatch({ type: "SET_ORDER_TYPE", orderType: type })}
              className={`px-4 py-2 text-sm font-medium transition-colors ${
                orderType === type
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {type === "MARKET" ? "시장가" : "지정가"}
            </button>
          ))}
        </div>
        {priceState === "loading" && (
          <div className="w-full sm:w-48 space-y-1">
            <div className="flex justify-between text-xs text-gray-500">
              <span>현재가 조회 중...</span>
              <span>{priceLoadProgress.loaded}/{priceLoadProgress.total}</span>
            </div>
            <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                style={{
                  width: priceLoadProgress.total > 0
                    ? `${(priceLoadProgress.loaded / priceLoadProgress.total) * 100}%`
                    : "0%"
                }}
              />
            </div>
          </div>
        )}
        {priceState === "error" && (
          <span className="text-xs text-amber-400 w-full sm:w-auto">
            현재가 조회 실패 — 지정가 직접 입력 가능
          </span>
        )}
      </div>

      {errorMsg && (
        <div className="rounded-lg bg-red-900/30 border border-red-700/50 px-4 py-3 text-xs text-red-300">
          {errorMsg}
        </div>
      )}

      {confirmed && (
        <p className="text-xs text-red-400 text-right">아래 버튼으로 즉시 주문이 실행됩니다.</p>
      )}

      {kisAccounts.length === 0 ? (
        <p className="text-sm text-gray-400 text-center py-4">연결된 KIS/키움 계좌가 없습니다.</p>
      ) : (
        <>
          {kisAccounts.map((acc) => {
            const sellRows = getSellRows(acc.id);
            const buyRows = getBuyRows(acc.id);
            const bState = balanceState[acc.id] ?? "idle";
            const unassignedBuyItems = actionableItems.filter(
              (i) =>
                (i.shares_to_trade ?? 0) > 0 &&
                !(buyAccounts[i.ticker] ?? []).includes(acc.id)
            );
            const hasData =
              sellRows.length > 0 || buyRows.length > 0 || unassignedBuyItems.length > 0;
            const { sells, buys } = getAccountSummary(acc.id);
            const cashAnalysis = exec.getCashAnalysis(acc.id);

            return (
              <div key={acc.id} className="border border-gray-700 rounded-xl overflow-hidden">
                {/* 계좌 헤더 */}
                <div className="bg-gray-800/70 px-4 py-2 flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0 sm:justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-medium text-white truncate">{acc.name}</span>
                    {acc.kis_account_no && (
                      <span className="text-xs text-gray-400 shrink-0">({acc.kis_account_no})</span>
                    )}
                    <span
                      className={`text-[11px] px-1.5 py-0.5 rounded font-medium shrink-0 ${
                        acc.is_mock_mode
                          ? "bg-yellow-900/40 text-yellow-400 border border-yellow-700/50"
                          : "bg-red-900/30 text-red-400 border border-red-700/40"
                      }`}
                    >
                      {acc.is_mock_mode ? "모의" : "실계좌"}
                    </span>
                    {!acc.is_active && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400 border border-gray-600 shrink-0">
                        비활성
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-gray-400">
                      {sells > 0 && <span className="text-blue-400">매도 {sells}건</span>}
                      {sells > 0 && buys > 0 && <span className="text-gray-600 mx-1">|</span>}
                      {buys > 0 && <span className="text-red-400">매수 {buys}건</span>}
                    </span>
                    {(state.orderableKrw[acc.id] != null || depositKrw[acc.id] != null) && (
                      <span className="text-[11px] text-gray-500">
                        {state.orderableKrw[acc.id] != null ? "주문가능" : "예수금"}{" "}
                        <span className="text-gray-300">
                          {fmtKrwPrice(state.orderableKrw[acc.id] ?? depositKrw[acc.id])}
                        </span>
                      </span>
                    )}
                    <button
                      onClick={() => loadLiveBalance(acc.id)}
                      disabled={bState === "loading"}
                      className="text-[11px] px-2 py-0.5 rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50 transition-colors border border-gray-600"
                    >
                      {bState === "loading"
                        ? "조회 중..."
                        : bState === "loaded"
                        ? "✓ 잔고 반영"
                        : bState === "not_found"
                        ? "계좌 없음"
                        : bState === "error"
                        ? "오류 (재시도)"
                        : "잔고 조회"}
                    </button>
                  </div>
                </div>

                <CashSummaryBar analysis={cashAnalysis} />

                {!hasData && bState !== "loaded" && (
                  <div className="px-4 py-3 text-xs text-gray-500 text-center">
                    분석 결과에 보유 종목이 없습니다. 잔고 조회로 실시간 보유 종목을 불러오세요.
                  </div>
                )}

                {hasData && (
                  <div>
                    {(sellRows.length > 0 || buyRows.length > 0) && (
                      <RebalancingOrderTable
                        accId={acc.id}
                        sellRows={sellRows}
                        buyRows={buyRows}
                        orderType={orderType}
                        priceState={priceState}
                        livePricesKrw={livePricesKrw}
                        livePricesUsd={livePricesUsd}
                        globalUsdRate={globalUsdRate}
                        selected={selected}
                        qtyOverrides={qtyOverrides}
                        buyAccounts={buyAccounts}
                        dispatch={dispatch}
                        getLimitPriceNative={getLimitPriceNative}
                        getEstimateKrw={getEstimateKrw}
                        getBuyTotalInfo={getBuyTotalInfo}
                      />
                    )}
                    {unassignedBuyItems.length > 0 && (
                      <div className="px-4 py-2 border-t border-gray-700/20">
                        <select
                          value=""
                          onChange={(e) => {
                            if (e.target.value)
                              dispatch({
                                type: "ADD_BUY_ACCOUNT",
                                ticker: e.target.value,
                                accountId: acc.id,
                              });
                          }}
                          className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-[11px] text-gray-400 focus:outline-none focus:border-indigo-500 hover:border-gray-600 cursor-pointer"
                        >
                          <option value="">+ 이 계좌에 매수 종목 추가</option>
                          {unassignedBuyItems.map((i) => (
                            <option key={i.ticker} value={i.ticker}>
                              {i.name} ({i.ticker}) — {Math.abs(Math.round(i.shares_to_trade!))}주
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {ordersCount === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">
              실행할 주문이 없습니다. 잔고 조회 후 주문을 선택하세요.
            </p>
          )}
        </>
      )}
    </>
  );
}
