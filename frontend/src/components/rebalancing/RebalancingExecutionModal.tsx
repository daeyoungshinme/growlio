import { AssetAccount } from "@/api/assets";
import { ExecutionResult, RebalancingAnalysis } from "@/api/rebalancing";
import { RebalancingResultSection } from "./RebalancingResultSection";
import { RebalancingConfirmStep } from "./RebalancingConfirmStep";
import { RebalancingExecutionContext, useRebalancingExecution } from "@/hooks/useRebalancingExecution";

interface Props {
  portfolioId: string;
  analysis: RebalancingAnalysis;
  accounts: AssetAccount[];
  onExecuted?: (results: ExecutionResult[]) => void;
  onClose: () => void;
}

export function RebalancingExecutionModal({ portfolioId, analysis, accounts, onExecuted, onClose }: Props) {
  const exec = useRebalancingExecution({ portfolioId, analysis, accounts, onExecuted });
  const { state, orders, dispatch } = exec;
  const { phase, results, confirmed, orderType } = state;

  return (
    <RebalancingExecutionContext.Provider value={exec}>
    <div className="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50 sm:p-4">
      <div className="bg-gray-900 border border-gray-700 rounded-t-2xl sm:rounded-2xl w-full sm:max-w-4xl max-h-[92vh] flex flex-col">
        <div className="shrink-0 flex items-center justify-between px-4 sm:px-6 py-3 border-b border-gray-700">
          <h2 className="text-base font-semibold text-white">리밸런싱 실행</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors text-xl leading-none">
            ×
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto px-4 sm:px-6 py-4 space-y-4">
          {phase === "confirm" && (
            <RebalancingConfirmStep
              ordersCount={orders.length}
            />
          )}

          {phase === "executing" && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <p className="text-sm text-gray-300">주문 실행 중...</p>
              <p className="text-xs text-gray-500">매도 주문 처리 후 매수 주문이 진행됩니다.</p>
            </div>
          )}

          {phase === "result" && <RebalancingResultSection results={results} />}
        </div>

        <div
          className="shrink-0 px-4 sm:px-6 py-3 border-t border-gray-700 flex flex-col-reverse sm:flex-row sm:justify-end gap-2 sm:gap-3"
          style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom, 0px))" }}
        >
          {phase === "confirm" && (
            <>
              <button
                onClick={onClose}
                className="w-full sm:w-auto px-4 py-2.5 sm:py-2 text-sm text-gray-300 border border-gray-600 rounded-lg hover:bg-gray-800 transition-colors"
              >
                취소
              </button>
              {confirmed ? (
                <button
                  onClick={exec.handleExecute}
                  disabled={orders.length === 0}
                  className="w-full sm:w-auto px-4 py-2.5 sm:py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  정말 실행할까요? ({orders.length}건)
                </button>
              ) : (
                <button
                  onClick={() => dispatch({ type: "CONFIRM_CLICK" })}
                  disabled={orders.length === 0}
                  className="w-full sm:w-auto px-4 py-2.5 sm:py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {orderType === "LIMIT" ? "지정가 " : "시장가 "}실행 ({orders.length}건)
                </button>
              )}
            </>
          )}
          {phase === "result" && (
            <button
              onClick={onClose}
              className="w-full sm:w-auto px-4 py-2.5 sm:py-2 text-sm bg-gray-700 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              닫기
            </button>
          )}
        </div>
      </div>
    </div>
    </RebalancingExecutionContext.Provider>
  );
}
