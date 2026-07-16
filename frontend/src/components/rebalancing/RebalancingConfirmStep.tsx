import { useRebalancingExecutionContext } from "@/hooks/useRebalancingExecution";
import { fmtKrw, fmtKrwPrice } from "@/utils/format";
import { PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";
import { STRATEGY_OPTIONS } from "@/constants/rebalancingConfig";
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
    retryPrice,
    loadAllPrices,
    hasRealAccount,
    globalCashSummary,
    autoAdjustForCash,
  } = exec;
  const {
    balanceState,
    depositKrw,
    priceState,
    priceRetrying,
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
      <div className="rounded-lg bg-yellow-50 border border-yellow-200 dark:bg-yellow-900/30 dark:border-yellow-700/50 px-4 py-3 text-xs text-yellow-800 dark:text-yellow-300">
        주문이 즉시 체결됩니다. 내용을 신중히 확인하세요.
      </div>

      {/* 실행 전략 선택 */}
      <div className="rounded-lg bg-gray-100 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700/50 px-4 py-3 space-y-2">
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300">실행 전략</p>
        <div className="space-y-1.5">
          {STRATEGY_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => dispatch({ type: "SET_STRATEGY", strategy: opt.value })}
              className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors border ${
                state.strategy === opt.value
                  ? "bg-indigo-100 dark:bg-indigo-600/30 border-indigo-300 dark:border-indigo-500/60 text-indigo-800 dark:text-indigo-200"
                  : "bg-white dark:bg-gray-700/40 border-gray-200 dark:border-gray-600/40 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/60"
              }`}
            >
              <span className="font-medium">{opt.label}</span>
              <span className="ml-2 text-gray-500 dark:text-gray-500">{opt.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {hasRealAccount && (
        <div className="rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/30 dark:border-red-700/50 px-4 py-3 text-xs text-red-700 dark:text-red-300 font-medium">
          실계좌 주문입니다. 실제 자금이 사용됩니다.
        </div>
      )}

      <div className="text-xs text-gray-500 dark:text-gray-500">
        시장이 닫혀 있을 경우 주문이 예약될 수 있습니다.
      </div>

      {errorMsg && (
        <div className="rounded-lg bg-red-50 border border-red-200 dark:bg-red-900/30 dark:border-red-700/50 px-4 py-3 text-xs text-red-700 dark:text-red-300">
          {errorMsg}
        </div>
      )}

      {confirmed && (
        <p className="text-xs text-red-600 dark:text-red-400 text-right">
          아래 버튼으로 즉시 주문이 실행됩니다.
        </p>
      )}

      {/* 전체 예수금 요약 배너 */}
      {globalCashSummary.balancesLoaded && (
        <div
          className={`rounded-xl p-3 space-y-2 ${
            globalCashSummary.isInsufficient
              ? "bg-red-50 border border-red-200 dark:bg-red-900/20 dark:border-red-800/40"
              : "bg-gray-100 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700/50"
          }`}
        >
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
            <span>
              전체 예수금{" "}
              <span className="text-gray-800 dark:text-gray-200 font-medium">
                {fmtKrw(globalCashSummary.totalDeposit ?? 0)}
              </span>
            </span>
            {(globalCashSummary.totalSellProceeds ?? 0) > 0 && (
              <span>
                + 매도예상{" "}
                <span className={`font-medium ${LOSS_COLOR}`}>
                  +{fmtKrw(globalCashSummary.totalSellProceeds ?? 0)}
                </span>
              </span>
            )}
            <span>
              사용가능{" "}
              <span className="text-gray-800 dark:text-gray-200 font-medium">
                {globalCashSummary.totalAvailable !== null
                  ? fmtKrw(globalCashSummary.totalAvailable)
                  : "—"}
              </span>
            </span>
            <span>
              매수필요{" "}
              <span className={`font-medium ${PROFIT_COLOR}`}>
                {globalCashSummary.totalBuyCost !== null
                  ? fmtKrw(globalCashSummary.totalBuyCost)
                  : "—"}
              </span>
            </span>
            <span
              className={`font-semibold ${
                globalCashSummary.surplus === null
                  ? "text-gray-500 dark:text-gray-400"
                  : globalCashSummary.surplus >= 0
                    ? "text-green-600 dark:text-green-400"
                    : "text-red-600 dark:text-red-400"
              }`}
            >
              {globalCashSummary.surplus === null
                ? "여유/부족 계산 불가"
                : globalCashSummary.surplus >= 0
                  ? `여유 +${fmtKrw(globalCashSummary.surplus)}`
                  : `부족 ${fmtKrw(globalCashSummary.surplus)}`}
            </span>
          </div>
          {globalCashSummary.isInsufficient && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-amber-700 dark:text-amber-300">
                예수금이 부족합니다. 매도 후 매수하거나 수량을 자동으로 조정할 수 있습니다.
              </span>
              <button
                onClick={autoAdjustForCash}
                className="shrink-0 text-xs bg-amber-200 dark:bg-amber-700/60 hover:bg-amber-300 dark:hover:bg-amber-700 text-amber-800 dark:text-amber-200 px-3 py-1.5 rounded-lg transition-colors font-medium border border-amber-300 dark:border-amber-600/40"
              >
                예수금에 맞춰 자동 조정
              </button>
            </div>
          )}
        </div>
      )}

      {kisAccounts.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
          연결된 KIS/키움 계좌가 없습니다.
        </p>
      ) : (
        <>
          {kisAccounts.map((acc) => {
            const sellRows = getSellRows(acc.id);
            const buyRows = getBuyRows(acc.id);
            const bState = balanceState[acc.id] ?? "idle";
            const unassignedBuyItems = actionableItems.filter(
              (i) =>
                (i.shares_to_trade ?? 0) > 0 && !(buyAccounts[i.ticker] ?? []).includes(acc.id),
            );
            const hasData =
              sellRows.length > 0 || buyRows.length > 0 || unassignedBuyItems.length > 0;
            const { sells, buys } = getAccountSummary(acc.id);
            const cashAnalysis = exec.getCashAnalysis(acc.id);

            return (
              <div
                key={acc.id}
                className="border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden"
              >
                {/* 계좌 헤더 */}
                <div className="bg-gray-100 dark:bg-gray-800/70 px-4 py-2 flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0 sm:justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {acc.name}
                    </span>
                    {acc.kis_account_no && (
                      <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                        ({acc.kis_account_no})
                      </span>
                    )}
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${
                        acc.is_mock_mode
                          ? "bg-yellow-100 text-yellow-700 border border-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-400 dark:border-yellow-700/50"
                          : "bg-red-100 text-red-700 border border-red-300 dark:bg-red-900/30 dark:text-red-400 dark:border-red-700/40"
                      }`}
                    >
                      {acc.is_mock_mode ? "모의" : "실계좌"}
                    </span>
                    {!acc.is_active && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 shrink-0">
                        비활성
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      {sells > 0 && (
                        <span className="text-blue-600 dark:text-blue-400">매도 {sells}건</span>
                      )}
                      {sells > 0 && buys > 0 && (
                        <span className="text-gray-400 dark:text-gray-600 mx-1">|</span>
                      )}
                      {buys > 0 && (
                        <span className="text-red-600 dark:text-red-400">매수 {buys}건</span>
                      )}
                    </span>
                    {(state.orderableKrw[acc.id] != null || depositKrw[acc.id] != null) && (
                      <span className="text-xs text-gray-500 dark:text-gray-500">
                        {state.orderableKrw[acc.id] != null ? "주문가능" : "예수금"}{" "}
                        <span className="text-gray-700 dark:text-gray-300">
                          {fmtKrwPrice(state.orderableKrw[acc.id] ?? depositKrw[acc.id])}
                        </span>
                      </span>
                    )}
                    <button
                      onClick={() => loadLiveBalance(acc.id)}
                      disabled={bState === "loading"}
                      className="text-xs px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50 transition-colors border border-gray-300 dark:border-gray-600"
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
                  <div className="px-4 py-3 text-xs text-gray-500 dark:text-gray-500 text-center">
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
                        priceRetrying={priceRetrying}
                        onRetryPrice={retryPrice}
                        onRetryAllPrices={() => void loadAllPrices()}
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
                      <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700/20">
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
                          className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded px-2 py-1 text-xs text-gray-500 dark:text-gray-400 focus:outline-none focus:border-indigo-500 hover:border-gray-400 dark:hover:border-gray-600 cursor-pointer"
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
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              실행할 주문이 없습니다. 잔고 조회 후 주문을 선택하세요.
            </p>
          )}
        </>
      )}
    </>
  );
}
