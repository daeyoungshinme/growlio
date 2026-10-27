import React from "react";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { RebalancingItem } from "@/api/rebalancing";
import { fmtKrw } from "@/utils/format";
import type { ExecutionAction, OrderType, PriceLoadState } from "@/hooks/useRebalancingExecution";
import { isOverseasMarket } from "@/constants/markets";
import { RebalancingMobileCard } from "./RebalancingMobileCard";
import {
  AllocationNote,
  BuyHoldingNote,
  DesktopOrderRow,
  type OrderRowModel,
  PriceErrorBanner,
  QtyInput,
  SectionLabel,
} from "./RebalancingOrderRows";
import { estimateLimitKrw, orderKey, type OrderSide } from "./rebalancingTradeMath";

function getNativePrice(
  ticker: string,
  market: string,
  livePricesKrw: Record<string, number>,
  livePricesUsd: Record<string, number>,
): number | undefined {
  return isOverseasMarket(market) ? livePricesUsd[ticker] : livePricesKrw[ticker];
}

export interface RebalancingOrderTableProps {
  accId: string;
  sellRows: { item: RebalancingItem; currentQty: number; suggestedQty: number }[];
  buyRows: { item: RebalancingItem; suggestedQty: number; currentQty: number }[];
  orderType: OrderType;
  priceState: PriceLoadState;
  livePricesKrw: Record<string, number>;
  livePricesUsd: Record<string, number>;
  priceRetrying: Set<string>;
  onRetryPrice: (ticker: string, market: string) => void;
  onRetryAllPrices: () => void;
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
  priceRetrying,
  onRetryPrice,
  onRetryAllPrices,
  globalUsdRate,
  selected,
  qtyOverrides,
  buyAccounts,
  dispatch,
  getLimitPriceNative,
  getEstimateKrw,
  getBuyTotalInfo,
}: RebalancingOrderTableProps) {
  const rowModel = (
    side: OrderSide,
    item: RebalancingItem,
    suggestedQty: number,
  ): OrderRowModel => {
    const key = orderKey(side, item.ticker, accId);
    const qty = qtyOverrides[key] ?? suggestedQty;
    const nativeLimitPrice = getLimitPriceNative(key, item.ticker, item.market);
    // 국내 대체 행(substitute_for)의 배분 정보는 원래 대표 종목 기준이다
    const baseTicker = item.substitute_for ?? item.ticker;
    const isMultiAccount = side === "buy" && (buyAccounts[baseTicker] ?? []).length > 1;
    const { allocated, needed } = isMultiAccount
      ? getBuyTotalInfo(baseTicker)
      : { allocated: 0, needed: 0 };
    return {
      key,
      qty,
      nativeLimitPrice,
      currentNativePrice: getNativePrice(item.ticker, item.market, livePricesKrw, livePricesUsd),
      est: getEstimateKrw(key, item.ticker, item.market, qty),
      estKrw: estimateLimitKrw(nativeLimitPrice, qty, item.market, globalUsdRate),
      isMultiAccount,
      allocated,
      needed,
    };
  };
  const removeBuyAccount = (item: RebalancingItem) =>
    dispatch({
      type: "REMOVE_BUY_ACCOUNT",
      ticker: item.substitute_for ?? item.ticker,
      accountId: accId,
      rowTicker: item.ticker,
    });

  const priceProps = {
    orderType,
    priceState,
    livePricesKrw,
    livePricesUsd,
    priceRetrying,
    onRetryPrice,
    globalUsdRate,
  };
  const colSpan = orderType === "LIMIT" ? 7 : 6;
  const marketEstimate = (est: number | null) =>
    est != null &&
    orderType === "MARKET" && (
      <div className="text-xs text-gray-500 dark:text-gray-500 mt-0.5 text-right">
        ≈ {fmtKrw(est)}
      </div>
    );

  return (
    <ErrorBoundary variant="section">
      {priceState === "error" && <PriceErrorBanner onRetry={onRetryAllPrices} />}
      {/* 모바일 카드 뷰 */}
      <div className="md:hidden divide-y divide-gray-200 dark:divide-gray-700/30">
        {sellRows.length > 0 && (
          <>
            <SectionLabel>매도</SectionLabel>
            {sellRows.map(({ item, currentQty, suggestedQty }) => {
              const row = rowModel("sell", item, suggestedQty);
              return (
                <RebalancingMobileCard
                  key={row.key}
                  orderKey={row.key}
                  item={item}
                  qty={row.qty}
                  isBuy={false}
                  maxQty={currentQty}
                  extra={
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5 text-right">
                      현재 {currentQty.toLocaleString()}주 보유
                    </p>
                  }
                  selected={selected}
                  {...priceProps}
                  nativeLimitPrice={row.nativeLimitPrice}
                  currentNativePrice={row.currentNativePrice}
                  estKrw={row.estKrw}
                  marketOrderEst={row.est}
                  dispatch={dispatch}
                />
              );
            })}
          </>
        )}
        {buyRows.length > 0 && (
          <>
            <SectionLabel>매수</SectionLabel>
            {buyRows.map(({ item, suggestedQty, currentQty }) => {
              const row = rowModel("buy", item, suggestedQty);
              return (
                <RebalancingMobileCard
                  key={row.key}
                  orderKey={row.key}
                  item={item}
                  qty={row.qty}
                  isBuy={true}
                  extra={
                    row.isMultiAccount ? (
                      <AllocationNote
                        allocated={row.allocated}
                        needed={row.needed}
                        unitTicker={item.substitute_for}
                      />
                    ) : (
                      <p className="text-xs text-gray-500 dark:text-gray-500 mt-0.5 text-right">
                        <BuyHoldingNote item={item} currentQty={currentQty} />
                      </p>
                    )
                  }
                  selected={selected}
                  {...priceProps}
                  nativeLimitPrice={row.nativeLimitPrice}
                  currentNativePrice={row.currentNativePrice}
                  estKrw={row.estKrw}
                  // 분할 매수는 배분 현황만 표시(데스크톱과 동일) — ≈ 추정액과 겹쳐 보이지 않게
                  marketOrderEst={row.isMultiAccount ? null : row.est}
                  onRemove={row.isMultiAccount ? () => removeBuyAccount(item) : undefined}
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
            <tr className="text-xs text-gray-500 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700/50">
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
          <tbody className="divide-y divide-gray-200 dark:divide-gray-700/30">
            {sellRows.length > 0 && (
              <>
                <tr>
                  <td
                    colSpan={colSpan}
                    className="px-4 py-1.5 text-xs text-gray-500 dark:text-gray-500 bg-gray-100 dark:bg-gray-800/30"
                  >
                    매도
                  </td>
                </tr>
                {sellRows.map(({ item, currentQty, suggestedQty }) => {
                  const row = rowModel("sell", item, suggestedQty);
                  return (
                    <DesktopOrderRow
                      key={row.key}
                      item={item}
                      row={row}
                      isBuy={false}
                      note={`현재 ${currentQty.toLocaleString()}주 보유`}
                      selected={selected.has(row.key)}
                      {...priceProps}
                      dispatch={dispatch}
                      qtyInput={
                        <QtyInput
                          value={row.qty}
                          max={currentQty}
                          colorClass="text-blue-600 dark:text-blue-400"
                          onChange={(qty) =>
                            dispatch({ type: "SET_QTY", key: row.key, qty, max: currentQty })
                          }
                        />
                      }
                      qtyFooter={marketEstimate(row.est)}
                      trailing={<td />}
                    />
                  );
                })}
              </>
            )}

            {buyRows.length > 0 && (
              <>
                <tr>
                  <td
                    colSpan={colSpan}
                    className="px-4 py-1.5 text-xs text-gray-500 dark:text-gray-500 bg-gray-100 dark:bg-gray-800/30"
                  >
                    매수
                  </td>
                </tr>
                {buyRows.map(({ item, suggestedQty, currentQty }) => {
                  const row = rowModel("buy", item, suggestedQty);
                  return (
                    <DesktopOrderRow
                      key={row.key}
                      item={item}
                      row={row}
                      isBuy={true}
                      note={<BuyHoldingNote item={item} currentQty={currentQty} />}
                      selected={selected.has(row.key)}
                      {...priceProps}
                      dispatch={dispatch}
                      qtyInput={
                        <QtyInput
                          value={row.qty}
                          colorClass="text-red-600 dark:text-red-400"
                          onChange={(qty) =>
                            dispatch({ type: "SET_QTY_AND_SELECT", key: row.key, qty })
                          }
                        />
                      }
                      qtyFooter={
                        row.isMultiAccount ? (
                          <AllocationNote
                            allocated={row.allocated}
                            needed={row.needed}
                            unitTicker={item.substitute_for}
                          />
                        ) : (
                          marketEstimate(row.est)
                        )
                      }
                      trailing={
                        <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={() => removeBuyAccount(item)}
                            disabled={!row.isMultiAccount}
                            title="이 계좌에서 제거"
                            aria-label="이 계좌에서 제거"
                            className="text-gray-400 dark:text-gray-600 hover:text-red-600 dark:hover:text-red-400 disabled:opacity-20 disabled:cursor-not-allowed transition-colors text-sm leading-none px-1"
                          >
                            ×
                          </button>
                        </td>
                      }
                    />
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
