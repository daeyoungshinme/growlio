import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bell, ChevronDown, ChevronUp, Loader2, RefreshCw } from "lucide-react";
import { BacktestResult, runBacktest } from "@/api/backtest";
import type { RebalancingAlert } from "@/api/alerts";
import type { Portfolio } from "@/api/portfolios";
import type { AssetAccount } from "@/api/assets";

import BacktestResultChart from "@/components/backtest/BacktestResultChart";
import BacktestMetricsTable from "@/components/backtest/BacktestMetricsTable";
import RebalancingTable from "@/components/rebalancing/RebalancingTable";
import { RebalancingAccountSyncSection } from "@/components/rebalancing/RebalancingAccountSyncSection";
import RebalancingStrategyCard from "@/components/rebalancing/RebalancingStrategyCard";
import FactorExposureChart from "@/components/portfolio-analysis/FactorExposureChart";
import EfficientFrontierChart from "@/components/portfolio-analysis/EfficientFrontierChart";
import ErrorBoundary from "@/components/ErrorBoundary";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { BACKTEST_DEFAULT_END_DATE } from "@/constants/defaults";
import { useAnalysisState } from "@/hooks/useAnalysisState";
import { useBacktestDateRange } from "@/hooks/useBacktestDateRange";

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
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const existingAlert = alertByPortfolioId[id];

  return (
    <div className="space-y-4">
      <RebalancingStrategyCard portfolioId={id} portfolioName={portfolio.name} />

      {/* 알림 설정 바 */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 p-3 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-sm">
        {existingAlert ? (
          <span className={`flex items-center gap-1.5 text-xs ${existingAlert.mode === "AUTO" ? "text-orange-600 dark:text-orange-400" : "text-blue-600 dark:text-blue-400"}`}>
            <Bell size={12} />
            {existingAlert.mode === "AUTO"
              ? `자동 실행 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`
              : `알림 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`}
          </span>
        ) : (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            이 포트폴리오에 자동화를 설정하시겠어요?
          </span>
        )}
        <button
          onClick={() => onOpenAlertModal(id)}
          className="self-end sm:self-auto text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap sm:ml-3"
        >
          {existingAlert ? "설정 변경" : "자동화 설정"}
        </button>
      </div>

      {/* 고급 분석 접이식 */}
      <div className="border border-gray-200 dark:border-gray-700 rounded-2xl overflow-hidden">
        <button
          onClick={() => setAdvancedOpen((v) => !v)}
          aria-expanded={advancedOpen}
          className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/50 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors min-h-[44px]"
        >
          <span>고급 분석</span>
          {advancedOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {advancedOpen && (
          <div className="p-4 space-y-4 bg-white dark:bg-gray-900">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <ErrorBoundary variant="section">
                <FactorExposureChart selectedPortfolioId={id} />
              </ErrorBoundary>
              <ErrorBoundary variant="section">
                <EfficientFrontierChart
                  comparePortfolioId={id}
                  comparePortfolioName={portfolio.name}
                />
              </ErrorBoundary>
            </div>
          </div>
        )}
      </div>
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
}

export function AnalysisPanel({
  selectedIds,
  selectedNames,
  portfolios,
  activeAccounts,
  onOpenAlertModal,
  autoAnalyzeId,
  alertByPortfolioId,
}: Props) {
  const selectedIdStr = Array.from(selectedIds).sort().join(",");
  const { mode, analysis, analyzing, error, triggerRebalancingAnalysis, setMode } =
    useAnalysisState({ autoAnalyzeId, selectedIdStr });
  const { startDate, endDate, activePreset, setStartDate, setEndDate, setPreset } =
    useBacktestDateRange();

  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [includeSpy, setIncludeSpy] = useState(true);
  const [includeReal, setIncludeReal] = useState(true);
  const [reinvestDividends, setReinvestDividends] = useState(true);

  const runMut = useMutation({
    mutationFn: () =>
      runBacktest({
        portfolio_ids: Array.from(selectedIds),
        start_date: startDate,
        end_date: endDate,
        include_spy: includeSpy,
        include_real_portfolio: includeReal,
        reinvest_dividends: reinvestDividends,
      }),
    onSuccess: (data) => setBacktestResult(data),
    onError: (e) => toast(extractErrorMessage(e, "백테스트 실행에 실패했습니다"), "error"),
  });

  function handleRebalancingAnalysis() {
    const [id] = Array.from(selectedIds);
    if (!id) return;
    void triggerRebalancingAnalysis(id);
  }

  const canRunBacktest = startDate < endDate && (selectedIds.size > 0 || includeSpy || includeReal);
  const canRebalance = selectedIds.size === 1;

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
          onClick={() => setMode("backtest")}
          className={`flex-none whitespace-nowrap flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            mode === "backtest"
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          }`}
        >
          백테스팅
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

      {/* 백테스팅 설정 패널 */}
      {mode === "backtest" && (
        <div className="card">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-400 dark:text-gray-500 font-medium mr-1">
                기간
              </span>
              {([1, 3, 5, 10] as const).map((y) => (
                <button
                  key={y}
                  onClick={() => setPreset(y)}
                  className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                    activePreset === y
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  {y}년
                </button>
              ))}
              <button
                onClick={() => setPreset(30)}
                className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                  activePreset === 30
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                }`}
              >
                최대
              </button>
            </div>
            <div className="flex flex-wrap gap-3">
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">
                  시작일
                </label>
                <input
                  type="date"
                  value={startDate}
                  max={endDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">
                  종료일
                </label>
                <input
                  type="date"
                  value={endDate}
                  min={startDate}
                  max={BACKTEST_DEFAULT_END_DATE}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeSpy}
                  onChange={(e) => setIncludeSpy(e.target.checked)}
                  className="rounded text-blue-600"
                />
                S&P 500 포함
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeReal}
                  onChange={(e) => setIncludeReal(e.target.checked)}
                  className="rounded text-blue-600"
                />
                실제 포트폴리오 포함
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={reinvestDividends}
                  onChange={(e) => setReinvestDividends(e.target.checked)}
                  className="rounded text-blue-600"
                />
                배당금 재투자
              </label>
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => {
                  setBacktestResult(null);
                  runMut.mutate();
                }}
                disabled={!canRunBacktest || runMut.isPending}
                aria-busy={runMut.isPending}
                className="w-full md:w-auto px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {runMut.isPending ? "계산 중..." : "▶ 백테스팅 실행"}
              </button>
            </div>
          </div>
          {runMut.isError && (
            <p className="mt-2 text-xs text-red-500">
              백테스팅 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.
            </p>
          )}
        </div>
      )}

      {/* 리밸런싱 결과 */}
      {mode === "rebalancing" && analysis && (
        <div className="card pb-20 sm:pb-0">
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-4">
            {analysis.portfolio_name} — 리밸런싱 분석
          </h3>
          {(() => {
            const p = portfolios.find((p) => p.id === analysis.portfolio_id);
            const analysisAccounts = p
              ? p.account_ids?.length
                ? activeAccounts.filter((a) => p.account_ids!.includes(a.id))
                : activeAccounts
              : [];
            return (
              <>
                <RebalancingTable
                  analysis={analysis}
                  portfolioId={analysis.portfolio_id}
                  accounts={analysisAccounts}
                  alertThreshold={alertByPortfolioId[analysis.portfolio_id.toString()]?.threshold_pct}
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
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mt-4 p-3 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-sm">
                {existingAlert ? (
                  <span
                    className={`flex items-center gap-1.5 text-xs ${existingAlert.mode === "AUTO" ? "text-orange-600 dark:text-orange-400" : "text-blue-600 dark:text-blue-400"}`}
                  >
                    <Bell size={12} />
                    {existingAlert.mode === "AUTO"
                      ? `자동 실행 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`
                      : `알림 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`}
                  </span>
                ) : (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    이 포트폴리오에 자동화를 설정하시겠어요?
                  </span>
                )}
                <button
                  onClick={() => onOpenAlertModal(portfolioIdStr)}
                  className="self-end sm:self-auto text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap sm:ml-3"
                >
                  {existingAlert ? "설정 변경" : "자동화 설정"}
                </button>
              </div>
            );
          })()}
        </div>
      )}
      {mode === "rebalancing" && error && (
        <div className="flex items-center justify-center h-48 text-sm text-red-500">{error}</div>
      )}

      {/* 백테스팅 결과 */}
      {mode === "backtest" && backtestResult && backtestResult.dates.length > 0 && (
        <div className="card space-y-6">
          <BacktestResultChart dates={backtestResult.dates} series={backtestResult.series} />
          <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
            <BacktestMetricsTable metrics={backtestResult.metrics} />
          </div>
        </div>
      )}
      {mode === "backtest" && backtestResult && backtestResult.dates.length === 0 && (
        <div className="card text-center text-sm text-gray-400 dark:text-gray-600 py-8">
          해당 기간의 가격 데이터가 없습니다. 기간을 조정해보세요.
        </div>
      )}

      {/* 전략 분석 결과 */}
      {mode === "strategy" &&
        (() => {
          const [id] = Array.from(selectedIds);
          const portfolio = portfolios.find((p) => p.id === id);
          if (!id || !portfolio) return null;
          return <StrategyAnalysisSection id={id} portfolio={portfolio} alertByPortfolioId={alertByPortfolioId} onOpenAlertModal={onOpenAlertModal} />;
        })()}

      {/* Empty state */}
      {!mode && selectedIds.size === 0 && (
        <div className="flex flex-col items-center justify-center h-48 text-center text-gray-400 dark:text-gray-500">
          <div className="text-3xl mb-3">📊</div>
          <div className="text-sm font-medium mb-1">포트폴리오를 선택하세요</div>
          <div className="text-xs">좌측 목록에서 포트폴리오를 클릭하면 분석을 시작할 수 있습니다</div>
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
              <div className="text-sm font-medium text-blue-700 dark:text-blue-300">리밸런싱 분석</div>
              <div className="text-xs text-blue-500 dark:text-blue-400 mt-0.5">비중 이탈 확인 및 매수/매도 수량 계산</div>
            </div>
            <span className="text-blue-400 text-lg">→</span>
          </button>
          <button
            onClick={() => setMode("backtest")}
            className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 hover:bg-gray-100 dark:hover:bg-gray-700/60 transition-colors"
          >
            <div className="text-left">
              <div className="text-sm font-medium text-gray-700 dark:text-gray-300">백테스팅</div>
              <div className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">목표 포트폴리오의 과거 수익률 시뮬레이션</div>
            </div>
            <span className="text-gray-400 text-lg">→</span>
          </button>
        </div>
      )}
    </div>
  );
}
