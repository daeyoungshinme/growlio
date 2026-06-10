import type { OrderType } from "@/hooks/useRebalancingExecution";
import { useRebalancingExecutionContext } from "@/hooks/useRebalancingExecution";
import { fmtKrwPrice } from "@/utils/format";
import { CashSummaryBar } from "./CashSummaryBar";
import { RebalancingOrderTable } from "./RebalancingOrderTable";

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
