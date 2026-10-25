import { RefreshCw } from "lucide-react";
import { AssetAccount } from "@/api/assets";
import { ExecutionResult, RebalancingAnalysis } from "@/api/rebalancing";
import { RebalancingResultSection } from "./RebalancingResultSection";
import { RebalancingConfirmStep } from "./RebalancingConfirmStep";
import {
  RebalancingExecutionContext,
  useRebalancingExecution,
} from "@/hooks/useRebalancingExecution";
import Modal from "@/components/common/Modal";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props {
  portfolioId: string;
  analysis: RebalancingAnalysis;
  accounts: AssetAccount[];
  onExecuted?: (results: ExecutionResult[]) => void;
  /** 결과 화면에서 계좌 동기화가 성공하면 호출 — 분석 재실행용 */
  onSynced?: () => void;
  onClose: () => void;
}

export function RebalancingExecutionModal({
  portfolioId,
  analysis,
  accounts,
  onExecuted,
  onSynced,
  onClose,
}: Props) {
  const exec = useRebalancingExecution({
    portfolioId,
    analysis,
    accounts,
    onExecuted,
  });
  const { state, orders, missingLimitPriceTickers, dispatch, loadAllPrices } = exec;
  const blocked = orders.length === 0 || missingLimitPriceTickers.length > 0;
  const { phase, results, confirmed, orderType, priceState, priceLoadProgress } = state;

  return (
    <RebalancingExecutionContext.Provider value={exec}>
      <Modal onClose={onClose} title="리밸런싱 실행" size="xl" avoidBottomNav>
        {phase === "confirm" && (
          <div className="shrink-0 px-4 sm:px-6 py-2.5 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex flex-wrap items-center gap-3">
            <span className="text-xs text-gray-500 dark:text-gray-400">주문 유형</span>
            <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {(["MARKET", "LIMIT"] as const).map((type) => (
                <button
                  key={type}
                  onClick={() => dispatch({ type: "SET_ORDER_TYPE", orderType: type })}
                  className={`px-4 py-2 text-sm font-medium transition-colors ${
                    orderType === type
                      ? "bg-indigo-600 text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
                  }`}
                >
                  {type === "MARKET" ? "시장가" : "지정가"}
                </button>
              ))}
            </div>
            {priceState === "loading" && (
              <div className="w-full sm:w-48 space-y-1">
                <div className="flex justify-between text-xs text-gray-500 dark:text-gray-500">
                  <span>현재가 조회 중...</span>
                  <span>
                    {priceLoadProgress.loaded}/{priceLoadProgress.total}
                  </span>
                </div>
                <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-300"
                    style={{
                      width:
                        priceLoadProgress.total > 0
                          ? `${(priceLoadProgress.loaded / priceLoadProgress.total) * 100}%`
                          : "0%",
                    }}
                  />
                </div>
              </div>
            )}
            {priceState === "error" && (
              <div className="w-full sm:w-auto flex items-center gap-2">
                <span className="text-xs text-amber-600 dark:text-amber-400">
                  현재가 조회 실패 — 지정가 직접 입력 가능
                </span>
                <button
                  onClick={() => void loadAllPrices()}
                  className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} shrink-0 gap-1 text-xs text-amber-700 dark:text-amber-300 hover:text-amber-600 dark:hover:text-amber-200 px-2 py-1 rounded bg-amber-100 dark:bg-amber-900/30 hover:bg-amber-200 dark:hover:bg-amber-900/50 border border-amber-300 dark:border-amber-700/40 transition-colors`}
                >
                  <RefreshCw size={12} />
                  재조회
                </button>
              </div>
            )}
          </div>
        )}

        <div className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
          {phase === "confirm" && <RebalancingConfirmStep ordersCount={orders.length} />}

          {phase === "executing" && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-700 dark:text-gray-300">주문 실행 중...</p>
              <div className="text-xs text-gray-500 dark:text-gray-500 space-y-1 text-center">
                <p>1. 매도 주문 처리 중</p>
                <p>2. 매도 완료 후 매수 주문 진행</p>
                <p className="text-amber-600 dark:text-amber-500/80 mt-2">창을 닫지 마세요</p>
              </div>
            </div>
          )}

          {phase === "result" && <RebalancingResultSection results={results} onSynced={onSynced} />}
        </div>

        {/* 시세를 불러오는 중엔 모든 종목이 '비어 있음'으로 잡힌다 — 위 로딩 배너로 충분하고 버튼은 계속 막혀 있다 */}
        {phase === "confirm" && priceState !== "loading" && missingLimitPriceTickers.length > 0 && (
          <p
            role="alert"
            className="shrink-0 px-4 sm:px-6 pt-3 text-xs text-red-600 dark:text-red-400"
          >
            지정가가 비어 있는 주문이 있습니다: {[...new Set(missingLimitPriceTickers)].join(", ")}{" "}
            — 가격을 입력하거나 선택을 해제하세요.
          </p>
        )}
        <div className="shrink-0 px-4 sm:px-6 py-3 border-t border-gray-200 dark:border-gray-700 flex flex-row gap-2">
          {phase === "confirm" && (
            <>
              {!confirmed ? (
                <>
                  <button
                    onClick={onClose}
                    className="shrink-0 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    취소
                  </button>
                  <button
                    onClick={() => dispatch({ type: "CONFIRM_CLICK" })}
                    disabled={blocked}
                    className="flex-1 px-4 py-2.5 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
                  >
                    {orderType === "LIMIT" ? "지정가" : "시장가"} 주문 확인 ({orders.length}건) →
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={() => dispatch({ type: "UNCONFIRM" })}
                    className="shrink-0 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    ← 수정
                  </button>
                  <button
                    onClick={exec.handleExecute}
                    disabled={blocked}
                    className="flex-1 px-4 py-2.5 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-semibold"
                  >
                    {orderType === "LIMIT" ? "지정가" : "시장가"} 최종 실행 ({orders.length}건)
                  </button>
                </>
              )}
            </>
          )}
          {phase === "result" && (
            <button
              onClick={onClose}
              className="w-full sm:w-auto px-4 py-2.5 sm:py-2 text-sm bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
            >
              닫기
            </button>
          )}
        </div>
      </Modal>
    </RebalancingExecutionContext.Provider>
  );
}
