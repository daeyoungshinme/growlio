import { useCallback, useEffect, useRef } from "react";
import { Loader2, RefreshCw } from "lucide-react";
import type { RebalancingAlert } from "@/api/alerts";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";
import { fetchBrokerBalance } from "@/api/rebalancing";

import RebalancingTable from "@/components/rebalancing/RebalancingTable";
import { RebalancingAccountSyncSection } from "@/components/rebalancing/RebalancingAccountSyncSection";
import RebalancingStrategyCard from "@/components/rebalancing/RebalancingStrategyCard";
import AutomationStatusBar from "@/components/rebalancing/AutomationStatusBar";
import { useAnalysisState } from "@/hooks/useAnalysisState";

function StrategyAnalysisSection({
  id,
  portfolio,
  alertByPortfolioId,
  onOpenAlertModal,
}: {
  id: string;
  portfolio: Portfolio;
  alertByPortfolioId: Record<string, RebalancingAlert>;
  onOpenAlertModal: (portfolioId: string) => void;
}) {
  const existingAlert = alertByPortfolioId[id];

  return (
    <div className="space-y-4">
      <RebalancingStrategyCard portfolioId={id} portfolioName={portfolio.name} />
      <AutomationStatusBar
        existingAlert={existingAlert}
        onOpenAlertModal={() => onOpenAlertModal(id)}
      />
    </div>
  );
}

interface Props {
  selectedIds: Set<string>;
  selectedNames: string;
  portfolios: Portfolio[];
  activeAccounts: AssetAccount[];
  onOpenAlertModal: (portfolioId: string) => void;
  autoAnalyzeId?: string;
  alertByPortfolioId: Record<string, RebalancingAlert>;
  autoOpenExecution?: boolean;
}

export function AnalysisPanel({
  selectedIds,
  selectedNames,
  portfolios,
  activeAccounts,
  onOpenAlertModal,
  autoAnalyzeId,
  alertByPortfolioId,
  autoOpenExecution,
}: Props) {
  const selectedIdStr = Array.from(selectedIds).sort().join(",");
  const { mode, analysis, analyzing, error, triggerRebalancingAnalysis, setMode } =
    useAnalysisState({ autoAnalyzeId, selectedIdStr });

  const analysisResultRef = useRef<HTMLDivElement>(null);
  const autoScrolledForRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    autoScrolledForRef.current = undefined;
  }, [autoAnalyzeId]);

  useEffect(() => {
    if (
      !autoAnalyzeId ||
      !analysis ||
      analysis.portfolio_id.toString() !== autoAnalyzeId ||
      autoScrolledForRef.current === autoAnalyzeId
    ) {
      return;
    }
    autoScrolledForRef.current = autoAnalyzeId;
    const timer = setTimeout(() => {
      analysisResultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
    return () => clearTimeout(timer);
  }, [autoAnalyzeId, analysis]);

  const canRebalance = selectedIds.size === 1;

  const handleRebalancingAnalysis = useCallback(async () => {
    const [id] = Array.from(selectedIds);
    if (!id) return;

    const currentPortfolio = portfolios.find((p) => p.id === id);
    const brokerAccounts = (
      currentPortfolio?.account_ids?.length
        ? activeAccounts.filter((a) => currentPortfolio.account_ids!.includes(a.id))
        : activeAccounts
    ).filter((a) => a.asset_type === "STOCK_KIS" || a.asset_type === "STOCK_KIWOOM");

    let depositKrwOverride: number | undefined;
    if (brokerAccounts.length > 0) {
      const results = await Promise.allSettled(brokerAccounts.map((a) => fetchBrokerBalance(a.id)));
      let total = 0;
      let hasSuccess = false;
      for (const r of results) {
        if (r.status === "fulfilled" && !r.value.error) {
          total += r.value.deposit_krw ?? 0;
          hasSuccess = true;
        }
      }
      if (hasSuccess) depositKrwOverride = total;
    }

    void triggerRebalancingAnalysis(id, depositKrwOverride);
  }, [selectedIds, portfolios, activeAccounts, triggerRebalancingAnalysis]);

  return (
    <div className="flex-1 min-w-0 space-y-4">
      {/* 분석 버튼 행 */}
      <div className="flex items-center gap-2 overflow-x-auto pb-0.5 [&::-webkit-scrollbar]:hidden">
        <button
          onClick={handleRebalancingAnalysis}
          disabled={!canRebalance || analyzing}
          title={!canRebalance ? "포트폴리오를 1개만 선택하세요" : undefined}
          className={`flex-none whitespace-nowrap flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 ${
            mode === "rebalancing"
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          }`}
        >
          {analyzing && mode === "rebalancing" ? (
            <>
              <Loader2 size={14} className="animate-spin" /> 분석 중...
            </>
          ) : (
            <>
              <RefreshCw size={14} /> 리밸런싱 분석
            </>
          )}
        </button>

        <button
          onClick={() => setMode("strategy")}
          disabled={!canRebalance}
          title={!canRebalance ? "포트폴리오를 1개만 선택하세요" : undefined}
          className={`flex-none whitespace-nowrap flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 ${
            mode === "strategy"
              ? "bg-amber-500 text-white hover:bg-amber-600"
              : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          }`}
        >
          전략 분석
        </button>

        {selectedIds.size > 0 && (
          <span className="flex-none whitespace-nowrap text-xs text-gray-400 dark:text-gray-500">
            {selectedNames}
            {selectedIds.size > 1 && ` 외 ${selectedIds.size - 1}개`} 선택됨
          </span>
        )}
      </div>

      {/* 리밸런싱 결과 */}
      {mode === "rebalancing" && analysis && (
        <div ref={analysisResultRef} className="card pb-20 sm:pb-0">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-4">
            {analysis.portfolio_name} — 리밸런싱 분석
          </h3>
          {(() => {
            const currentPortfolio = portfolios.find(
              (p) => p.id === analysis.portfolio_id.toString(),
            );
            const analysisAccounts = currentPortfolio?.account_ids?.length
              ? activeAccounts.filter((a) => currentPortfolio.account_ids!.includes(a.id))
              : activeAccounts;
            return (
              <>
                <RebalancingTable
                  analysis={analysis}
                  portfolioId={analysis.portfolio_id}
                  accounts={analysisAccounts}
                  alertThreshold={
                    alertByPortfolioId[analysis.portfolio_id.toString()]?.threshold_pct
                  }
                  autoOpenExecution={autoOpenExecution}
                />
                <RebalancingAccountSyncSection
                  accounts={analysisAccounts}
                  onReanalyze={() => triggerRebalancingAnalysis(analysis.portfolio_id)}
                />
              </>
            );
          })()}
          {(() => {
            const portfolioIdStr = analysis.portfolio_id.toString();
            const existingAlert = alertByPortfolioId[portfolioIdStr];
            return (
              <div className="mt-4">
                <AutomationStatusBar
                  existingAlert={existingAlert}
                  onOpenAlertModal={() => onOpenAlertModal(portfolioIdStr)}
                />
              </div>
            );
          })()}
        </div>
      )}
      {mode === "rebalancing" && error && (
        <div className="flex items-center justify-center h-48 text-sm text-red-500">{error}</div>
      )}

      {/* 전략 분석 결과 */}
      {mode === "strategy" &&
        (() => {
          const [id] = Array.from(selectedIds);
          const portfolio = portfolios.find((p) => p.id === id);
          if (!id || !portfolio) return null;
          return (
            <StrategyAnalysisSection
              id={id}
              portfolio={portfolio}
              alertByPortfolioId={alertByPortfolioId}
              onOpenAlertModal={onOpenAlertModal}
            />
          );
        })()}

      {/* Empty state */}
      {!mode && selectedIds.size === 0 && (
        <div className="flex flex-col items-center justify-center h-48 text-center text-gray-400 dark:text-gray-500">
          <div className="text-3xl mb-3">📊</div>
          <div className="text-sm font-medium mb-1">포트폴리오를 선택하세요</div>
          <div className="text-xs">
            좌측 목록에서 포트폴리오를 클릭하면 분석을 시작할 수 있습니다
          </div>
        </div>
      )}
      {!mode && selectedIds.size > 0 && (
        <div className="flex flex-col gap-2">
          <button
            onClick={handleRebalancingAnalysis}
            disabled={!canRebalance || analyzing}
            className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors disabled:opacity-40"
          >
            <div className="text-left">
              <div className="text-sm font-medium text-blue-700 dark:text-blue-300">
                리밸런싱 분석
              </div>
              <div className="text-xs text-blue-500 dark:text-blue-400 mt-0.5">
                비중 이탈 확인 및 매수/매도 수량 계산
              </div>
            </div>
            <span className="text-blue-400 text-lg">→</span>
          </button>
        </div>
      )}
    </div>
  );
}
