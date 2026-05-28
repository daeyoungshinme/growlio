import { AssetAccount } from "../../api/assets";
import { RebalancingItem } from "../../api/rebalancing";
import { fmtKrw, fmtKrwPrice } from "../../utils/format";
import { SideBadge } from "./RebalancingBadges";
import { ExecutionAction, ExecutionState, OrderType, isOverseasMarket } from "./useRebalancingExecution";

interface Props {
  kisAccounts: AssetAccount[];
  actionableItems: RebalancingItem[];
  state: ExecutionState;
  dispatch: React.Dispatch<ExecutionAction>;
  getSellRows: (accountId: string) => { item: RebalancingItem; currentQty: number; suggestedQty: number }[];
  getBuyRows: (accountId: string) => { item: RebalancingItem; suggestedQty: number; currentQty: number }[];
  getBuyTotalInfo: (ticker: string) => { allocated: number; needed: number };
  getAccountSummary: (accountId: string) => { sells: number; buys: number };
  getLimitPriceNative: (key: string, ticker: string, market: string) => number;
  getEstimateKrw: (key: string, ticker: string, market: string, qty: number) => number | null;
  loadLiveBalance: (accountId: string) => Promise<void>;
  hasRealAccount: boolean;
  ordersCount: number;
}

export function RebalancingConfirmStep({
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
  ordersCount,
}: Props) {
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

  function renderPriceCell(ticker: string, market: string) {
    const krw = livePricesKrw[ticker];
    const usd = livePricesUsd[ticker];
    if (priceState === "loading") return <span className="text-gray-600 text-[11px]">조회 중</span>;
    if (krw != null) {
      if (isOverseasMarket(market) && usd != null) {
        return (
          <div>
            <div className="text-gray-300 text-[11px]">${usd.toFixed(2)}</div>
            <div className="text-gray-500 text-[11px]">≈ {fmtKrwPrice(krw)}</div>
          </div>
        );
      }
      return <span className="text-gray-300 text-[11px]">{fmtKrwPrice(krw)}</span>;
    }
    return <span className="text-gray-600 text-[11px]">—</span>;
  }

  function renderLimitPriceCell(key: string, ticker: string, market: string, qty: number) {
    if (orderType !== "LIMIT") return <td />;
    const overseas = isOverseasMarket(market);
    const nativeVal = getLimitPriceNative(key, ticker, market);
    const estKrw = overseas && globalUsdRate != null ? nativeVal * globalUsdRate * qty : nativeVal * qty;
    return (
      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-end gap-1">
          <input
            type="number"
            min={0}
            step={overseas ? 0.01 : 1}
            value={nativeVal || ""}
            placeholder={overseas ? "USD" : "KRW"}
            onChange={(e) => dispatch({ type: "SET_LIMIT_PRICE", key, price: parseFloat(e.target.value) || 0 })}
            className="w-20 bg-gray-800 border border-indigo-600/50 rounded px-2 py-0.5 text-right text-indigo-300 font-medium text-[11px] focus:outline-none focus:border-indigo-500"
          />
          <span className="text-gray-500 text-[11px]">{overseas ? "USD" : "원"}</span>
        </div>
        {nativeVal > 0 && (
          <div className="text-[11px] text-gray-600 mt-0.5 text-right">
            ≈ {fmtKrw(overseas && globalUsdRate != null ? nativeVal * globalUsdRate : nativeVal)} × {qty}주 = {fmtKrw(estKrw)}
          </div>
        )}
      </td>
    );
  }

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

      <div className="flex items-center gap-3">
        <span className="text-xs text-gray-400">주문 유형</span>
        <div className="flex rounded-lg border border-gray-700 overflow-hidden">
          {(["MARKET", "LIMIT"] as OrderType[]).map((type) => (
            <button
              key={type}
              onClick={() => dispatch({ type: "SET_ORDER_TYPE", orderType: type })}
              className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                orderType === type ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {type === "MARKET" ? "시장가" : "지정가"}
            </button>
          ))}
        </div>
        {priceState === "loading" && (
          <span className="text-xs text-gray-500">
            현재가 조회 중... ({priceLoadProgress.loaded}/{priceLoadProgress.total})
          </span>
        )}
        {priceState === "error" && (
          <span className="text-xs text-amber-400">현재가 조회 실패 — 지정가 직접 입력 가능</span>
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
              (i) => (i.shares_to_trade ?? 0) > 0 && !(buyAccounts[i.ticker] ?? []).includes(acc.id)
            );
            const hasData = sellRows.length > 0 || buyRows.length > 0 || unassignedBuyItems.length > 0;
            const { sells, buys } = getAccountSummary(acc.id);

            return (
              <div key={acc.id} className="border border-gray-700 rounded-xl overflow-hidden">
                <div className="bg-gray-800/70 px-4 py-2.5 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-white">{acc.name}</span>
                    {acc.kis_account_no && (
                      <span className="text-xs text-gray-400">({acc.kis_account_no})</span>
                    )}
                    <span
                      className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
                        acc.is_mock_mode
                          ? "bg-yellow-900/40 text-yellow-400 border border-yellow-700/50"
                          : "bg-red-900/30 text-red-400 border border-red-700/40"
                      }`}
                    >
                      {acc.is_mock_mode ? "모의" : "실계좌"}
                    </span>
                    {!acc.is_active && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-gray-700 text-gray-400 border border-gray-600">
                        비활성
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">
                      {sells > 0 && <span className="text-blue-400">매도 {sells}건</span>}
                      {sells > 0 && buys > 0 && <span className="text-gray-600 mx-1">|</span>}
                      {buys > 0 && <span className="text-red-400">매수 {buys}건</span>}
                    </span>
                    {depositKrw[acc.id] != null && (
                      <span className="text-[11px] text-gray-500">
                        예수금 <span className="text-gray-300">{fmtKrw(depositKrw[acc.id])}</span>
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

                {!hasData && bState !== "loaded" && (
                  <div className="px-4 py-3 text-xs text-gray-500 text-center">
                    분석 결과에 보유 종목이 없습니다. 잔고 조회로 실시간 보유 종목을 불러오세요.
                  </div>
                )}

                {hasData && (
                  <div>
                    {(sellRows.length > 0 || buyRows.length > 0) && (
                      <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                          <colgroup>
                            <col style={{ width: "32px" }} />
                            <col />
                            <col style={{ width: "56px" }} />
                            <col style={{ width: "110px" }} />
                            <col style={{ width: "140px" }} />
                            {orderType === "LIMIT" && <col style={{ width: "176px" }} />}
                            <col style={{ width: "32px" }} />
                          </colgroup>
                          <thead>
                            <tr className="text-[11px] text-gray-500 border-b border-gray-700/50">
                              <th />
                              <th className="px-3 py-2 text-left font-normal">종목</th>
                              <th className="px-3 py-2 text-center font-normal">구분</th>
                              <th className="px-2 py-2 text-right font-normal">현재가</th>
                              <th className="px-3 py-2 text-right font-normal">수량</th>
                              {orderType === "LIMIT" && <th className="px-2 py-2 text-right font-normal">지정가</th>}
                              <th />
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-700/30">
                            {sellRows.length > 0 && (
                              <>
                                <tr>
                                  <td colSpan={orderType === "LIMIT" ? 7 : 6} className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30">
                                    매도
                                  </td>
                                </tr>
                                {sellRows.map(({ item, currentQty, suggestedQty }) => {
                                  const key = `sell_${item.ticker}_${acc.id}`;
                                  const qty = qtyOverrides[key] ?? suggestedQty;
                                  const est = getEstimateKrw(key, item.ticker, item.market, qty);
                                  return (
                                    <tr key={key} className="hover:bg-gray-800/40 cursor-pointer" onClick={() => dispatch({ type: "TOGGLE_SELECTED", key })}>
                                      <td className="px-3 py-2">
                                        <input type="checkbox" checked={selected.has(key)} onChange={() => dispatch({ type: "TOGGLE_SELECTED", key })} onClick={(e) => e.stopPropagation()} className="accent-indigo-500" />
                                      </td>
                                      <td className="px-3 py-2">
                                        <div className="text-white font-medium truncate max-w-[120px]">{item.name}</div>
                                        <div className="text-gray-400 text-[11px]">{item.ticker}</div>
                                        <div className="text-gray-500 text-[11px]">현재 {currentQty.toLocaleString()}주 보유</div>
                                      </td>
                                      <td className="px-3 py-2 text-center"><SideBadge isBuy={false} /></td>
                                      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>{renderPriceCell(item.ticker, item.market)}</td>
                                      <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                        <div className="flex items-center justify-end gap-1">
                                          <input type="number" min={0} value={qty} onChange={(e) => dispatch({ type: "SET_QTY", key, qty: parseInt(e.target.value) || 0 })} className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-blue-400 font-medium focus:outline-none focus:border-indigo-500" />
                                          <span className="text-gray-400">주</span>
                                        </div>
                                        {est != null && orderType === "MARKET" && (
                                          <div className="text-[11px] text-gray-500 mt-0.5 text-right">≈ {fmtKrw(est)}</div>
                                        )}
                                      </td>
                                      {renderLimitPriceCell(key, item.ticker, item.market, qty)}
                                      <td />
                                    </tr>
                                  );
                                })}
                              </>
                            )}

                            {buyRows.length > 0 && (
                              <>
                                <tr>
                                  <td colSpan={orderType === "LIMIT" ? 7 : 6} className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-800/30">
                                    매수
                                  </td>
                                </tr>
                                {buyRows.map(({ item, suggestedQty, currentQty }) => {
                                  const key = `buy_${item.ticker}_${acc.id}`;
                                  const qty = qtyOverrides[key] ?? suggestedQty;
                                  const est = getEstimateKrw(key, item.ticker, item.market, qty);
                                  const isMultiAccount = (buyAccounts[item.ticker] ?? []).length > 1;
                                  const isOnlyAccount = !isMultiAccount;
                                  const { allocated, needed } = isMultiAccount ? getBuyTotalInfo(item.ticker) : { allocated: 0, needed: 0 };
                                  return (
                                    <tr key={key} className="hover:bg-gray-800/40 cursor-pointer" onClick={() => dispatch({ type: "TOGGLE_SELECTED", key })}>
                                      <td className="px-3 py-2">
                                        <input type="checkbox" checked={selected.has(key)} onChange={() => dispatch({ type: "TOGGLE_SELECTED", key })} onClick={(e) => e.stopPropagation()} className="accent-indigo-500" />
                                      </td>
                                      <td className="px-3 py-2">
                                        <div className="text-white font-medium truncate max-w-[120px]">{item.name}</div>
                                        <div className="text-gray-400 text-[11px]">{item.ticker}</div>
                                        <div className="text-gray-500 text-[11px]">
                                          {currentQty > 0 ? `현재 ${currentQty.toLocaleString()}주 보유` : "현재 미보유"}
                                        </div>
                                      </td>
                                      <td className="px-3 py-2 text-center"><SideBadge isBuy={true} /></td>
                                      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>{renderPriceCell(item.ticker, item.market)}</td>
                                      <td className="px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                        <div className="flex items-center justify-end gap-1">
                                          <input type="number" min={0} value={qty} onChange={(e) => dispatch({ type: "SET_QTY_AND_SELECT", key, qty: parseInt(e.target.value) || 0 })} className="w-16 bg-gray-800 border border-gray-600 rounded px-2 py-0.5 text-right text-red-400 font-medium focus:outline-none focus:border-indigo-500" />
                                          <span className="text-gray-400">주</span>
                                        </div>
                                        {isMultiAccount ? (
                                          <div className={`text-[11px] mt-0.5 text-right ${allocated === needed ? "text-gray-500" : "text-amber-400"}`}>
                                            배분 {allocated} / {needed}주
                                          </div>
                                        ) : (
                                          est != null && orderType === "MARKET" && (
                                            <div className="text-[11px] text-gray-500 mt-0.5 text-right">≈ {fmtKrw(est)}</div>
                                          )
                                        )}
                                      </td>
                                      {renderLimitPriceCell(key, item.ticker, item.market, qty)}
                                      <td className="px-2 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                                        <button
                                          onClick={() => dispatch({ type: "REMOVE_BUY_ACCOUNT", ticker: item.ticker, accountId: acc.id })}
                                          disabled={isOnlyAccount}
                                          title="이 계좌에서 제거"
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
                    )}
                    {unassignedBuyItems.length > 0 && (
                      <div className="px-4 py-2 border-t border-gray-700/20">
                        <select
                          value=""
                          onChange={(e) => { if (e.target.value) dispatch({ type: "ADD_BUY_ACCOUNT", ticker: e.target.value, accountId: acc.id }); }}
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
