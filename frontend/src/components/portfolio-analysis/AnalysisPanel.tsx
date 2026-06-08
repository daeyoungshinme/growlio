import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bell, Loader2, RefreshCw } from "lucide-react";
import { BacktestResult, CorrelationResult, runBacktest, runCorrelation } from "../../api/backtest";
import { analyzePortfolio, RebalancingAnalysis } from "../../api/rebalancing";
import { fetchRebalancingAlerts } from "../../api/alerts";
import type { Portfolio } from "../../api/portfolios";
import type { AssetAccount } from "../../api/assets";
import BacktestResultChart from "../backtest/BacktestResultChart";
import BacktestMetricsTable from "../backtest/BacktestMetricsTable";
import CorrelationHeatmap from "../backtest/CorrelationHeatmap";
import RebalancingTable from "../rebalancing/RebalancingTable";
import { toast } from "../../utils/toast";
import { extractErrorMessage } from "../../utils/error";
import { QUERY_KEYS } from "../../constants/queryKeys";
import { STALE_TIME } from "../../constants/queryConfig";
import { BACKTEST_DEFAULT_END_DATE, BACKTEST_DEFAULT_START_DATE } from "../../constants/defaults";

interface Props {
  selectedIds: Set<string>;
  selectedNames: string;
  portfolios: Portfolio[];
  activeAccounts: AssetAccount[];
  onOpenAlertModal: (portfolioId: string) => void;
}

type AnalysisMode = "rebalancing" | "backtest";

export function AnalysisPanel({ selectedIds, selectedNames, portfolios, activeAccounts, onOpenAlertModal }: Props) {
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode | null>(null);
  const [analysis, setAnalysis] = useState<RebalancingAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [correlationResult, setCorrelationResult] = useState<CorrelationResult | null>(null);
  const [correlationLoading, setCorrelationLoading] = useState(false);
  const [startDate, setStartDate] = useState(BACKTEST_DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(BACKTEST_DEFAULT_END_DATE);
  const [activePreset, setActivePreset] = useState<number | null>(5);
  const [includeSpy, setIncludeSpy] = useState(true);
  const [includeReal, setIncludeReal] = useState(true);
  const [reinvestDividends, setReinvestDividends] = useState(true);
  const { data: rebalancingAlerts = [] } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const alertByPortfolioId = Object.fromEntries(rebalancingAlerts.map((a) => [a.portfolio_id, a]));

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

  async function handleRebalancingAnalysis() {
    const [id] = Array.from(selectedIds);
    if (!id) return;
    setAnalysisMode("rebalancing");
    setBacktestResult(null);
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysis(null);
    try {
      const result = await analyzePortfolio(id);
      setAnalysis(result);
    } catch (err) {
      setAnalysisError(extractErrorMessage(err, "분석 중 오류가 발생했습니다."));
    } finally {
      setAnalyzing(false);
    }
  }

  function handleSwitchToBacktest() {
    setAnalysisMode("backtest");
    setAnalysis(null);
    setAnalysisError(null);
    setCorrelationResult(null);
  }

  const canRunBacktest = startDate < endDate && (selectedIds.size > 0 || includeSpy || includeReal);
  const canRebalance = selectedIds.size === 1;

  return (
    <div className="flex-1 min-w-0 space-y-4">
      {/* 분석 버튼 행 */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={handleRebalancingAnalysis}
          disabled={!canRebalance || analyzing}
          title={!canRebalance ? "포트폴리오를 1개만 선택하세요" : undefined}
          className={`flex-1 md:flex-none flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 ${
            analysisMode === "rebalancing"
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          }`}
        >
          {analyzing && analysisMode === "rebalancing" ? (
            <><Loader2 size={14} className="animate-spin" /> 분석 중...</>
          ) : (
            <><RefreshCw size={14} /> 리밸런싱 분석</>
          )}
        </button>

        <button
          onClick={handleSwitchToBacktest}
          className={`flex-1 md:flex-none flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
            analysisMode === "backtest"
              ? "bg-blue-600 text-white hover:bg-blue-700"
              : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
          }`}
        >
          백테스팅
        </button>

        {selectedIds.size > 0 && (
          <span className="w-full md:w-auto text-xs text-gray-400 dark:text-gray-500">
            {selectedNames}
            {selectedIds.size > 1 && ` 외 ${selectedIds.size - 1}개`} 선택됨
          </span>
        )}
      </div>

      {/* 백테스팅 설정 패널 */}
      {analysisMode === "backtest" && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-gray-400 dark:text-gray-500 font-medium mr-1">기간</span>
              {([1, 3, 5, 10] as const).map((y) => {
                const isActive = activePreset === y;
                return (
                  <button
                    key={y}
                    onClick={() => {
                      const end = BACKTEST_DEFAULT_END_DATE;
                      const start = `${new Date().getFullYear() - y}-${String(new Date().getMonth() + 1).padStart(2, "0")}-${String(new Date().getDate()).padStart(2, "0")}`;
                      setStartDate(start);
                      setEndDate(end);
                      setActivePreset(y);
                    }}
                    className={`px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                      isActive
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700"
                    }`}
                  >
                    {y}년
                  </button>
                );
              })}
              <button
                onClick={() => {
                  const end = BACKTEST_DEFAULT_END_DATE;
                  const start = `${new Date().getFullYear() - 30}-01-01`;
                  setStartDate(start);
                  setEndDate(end);
                  setActivePreset(30);
                }}
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
                <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">시작일</label>
                <input
                  type="date"
                  value={startDate}
                  max={endDate}
                  onChange={(e) => { setStartDate(e.target.value); setActivePreset(null); }}
                  className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">종료일</label>
                <input
                  type="date"
                  value={endDate}
                  min={startDate}
                  max={BACKTEST_DEFAULT_END_DATE}
                  onChange={(e) => { setEndDate(e.target.value); setActivePreset(null); }}
                  className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input type="checkbox" checked={includeSpy} onChange={(e) => setIncludeSpy(e.target.checked)} className="rounded text-blue-600" />
                S&P 500 포함
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input type="checkbox" checked={includeReal} onChange={(e) => setIncludeReal(e.target.checked)} className="rounded text-blue-600" />
                실제 포트폴리오 포함
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                <input type="checkbox" checked={reinvestDividends} onChange={(e) => setReinvestDividends(e.target.checked)} className="rounded text-blue-600" />
                배당금 재투자
              </label>
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => { setBacktestResult(null); setCorrelationResult(null); runMut.mutate(); }}
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
      {analysisMode === "rebalancing" && analysis && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
              {analysis.portfolio_name} — 리밸런싱 분석
            </h3>
            <button
              onClick={handleRebalancingAnalysis}
              disabled={analyzing}
              className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 px-2 py-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <RefreshCw size={12} /> 다시 분석
            </button>
          </div>
          <RebalancingTable
            analysis={analysis}
            portfolioId={analysis.portfolio_id}
            accounts={(() => {
              const p = portfolios.find((p) => selectedIds.has(p.id));
              return p?.account_ids?.length
                ? activeAccounts.filter((a) => p.account_ids!.includes(a.id))
                : activeAccounts;
            })()}
            existingAlert={alertByPortfolioId[analysis.portfolio_id.toString()]}
            onAlertClick={() => onOpenAlertModal(analysis.portfolio_id.toString())}
          />
          {(() => {
            const portfolioIdStr = analysis.portfolio_id.toString();
            const existingAlert = alertByPortfolioId[portfolioIdStr];
            return (
              <div className="hidden sm:flex items-center justify-between mt-4 p-3 rounded-xl border border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-900 text-sm">
                {existingAlert ? (
                  <span className={`flex items-center gap-1.5 text-xs ${existingAlert.mode === "AUTO" ? "text-orange-600 dark:text-orange-400" : "text-blue-600 dark:text-blue-400"}`}>
                    <Bell size={12} />
                    {existingAlert.mode === "AUTO"
                      ? `자동 실행 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`
                      : `알림 설정됨 (±${existingAlert.threshold_pct}% 이탈 시)`}
                  </span>
                ) : (
                  <span className="text-xs text-gray-500 dark:text-gray-400">이 포트폴리오에 자동화를 설정하시겠어요?</span>
                )}
                <button
                  onClick={() => onOpenAlertModal(portfolioIdStr)}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline whitespace-nowrap ml-3"
                >
                  {existingAlert ? "설정 변경" : "자동화 설정"}
                </button>
              </div>
            );
          })()}
        </div>
      )}
      {analysisMode === "rebalancing" && analysisError && (
        <div className="flex items-center justify-center h-48 text-sm text-red-500">
          {analysisError}
        </div>
      )}

      {/* 백테스팅 결과 */}
      {analysisMode === "backtest" && backtestResult && backtestResult.dates.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 space-y-6">
          <BacktestResultChart dates={backtestResult.dates} series={backtestResult.series} />
          <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
            <BacktestMetricsTable metrics={backtestResult.metrics} />
          </div>
          <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
            {correlationResult ? (
              <CorrelationHeatmap result={correlationResult} />
            ) : (
              <div className="flex justify-center">
                <button
                  onClick={async () => {
                    if (!selectedIds.size) return;
                    setCorrelationLoading(true);
                    try {
                      const res = await runCorrelation({
                        portfolio_ids: Array.from(selectedIds),
                        start_date: startDate,
                        end_date: endDate,
                      });
                      setCorrelationResult(res);
                    } catch {
                      toast("상관관계 분석에 실패했습니다");
                    } finally {
                      setCorrelationLoading(false);
                    }
                  }}
                  disabled={correlationLoading || !selectedIds.size}
                  className="flex items-center gap-2 px-4 py-2 text-xs text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-40"
                >
                  {correlationLoading ? <><Loader2 size={12} className="animate-spin" /> 분석 중...</> : "📊 종목 간 상관관계 분석"}
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      {analysisMode === "backtest" && backtestResult && backtestResult.dates.length === 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 text-center text-sm text-gray-400 dark:text-gray-600 py-8">
          해당 기간의 가격 데이터가 없습니다. 기간을 조정해보세요.
        </div>
      )}

      {/* Empty state */}
      {!analysisMode && (
        <div className="flex flex-col items-center justify-center h-64 text-center text-gray-400 dark:text-gray-500">
          <div className="text-4xl mb-3">📊</div>
          <div className="text-sm font-medium mb-1">포트폴리오를 선택하고 분석하세요</div>
          <div className="text-xs">좌측에서 포트폴리오를 선택한 후 리밸런싱 분석 또는 백테스팅을 실행하세요</div>
        </div>
      )}

    </div>
  );
}
