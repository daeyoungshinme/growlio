import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit2, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { BacktestResult, runBacktest } from "../../api/backtest";
import { analyzePortfolio, RebalancingAnalysis } from "../../api/rebalancing";
import {
  Portfolio,
  PortfolioItem,
  createPortfolio,
  deletePortfolio,
  fetchPortfolios,
  updatePortfolio,
} from "../../api/portfolios";
import { fetchAccounts } from "../../api/assets";
import UnifiedPortfolioEditor from "../portfolios/UnifiedPortfolioEditor";
import BacktestResultChart from "../backtest/BacktestResultChart";
import BacktestMetricsTable from "../backtest/BacktestMetricsTable";
import RebalancingTable from "../rebalancing/RebalancingTable";
import { toast } from "../../utils/toast";

const today = new Date().toISOString().slice(0, 10);
const fiveYearsAgo = `${new Date().getFullYear() - 5}-01-01`;

type AnalysisMode = "rebalancing" | "backtest";

export default function PortfolioAnalysisTab() {
  const qc = useQueryClient();

  const { data: portfolios = [], isLoading } = useQuery({
    queryKey: ["portfolios"],
    queryFn: fetchPortfolios,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts"],
    queryFn: fetchAccounts,
  });
  const activeAccounts = accounts.filter((a) => a.is_active);
  const stockAccounts = activeAccounts.filter((a) =>
    ["STOCK_KIS", "STOCK_OTHER"].includes(a.asset_type)
  );

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [analysisMode, setAnalysisMode] = useState<AnalysisMode | null>(null);

  const [analysis, setAnalysis] = useState<RebalancingAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);

  const [startDate, setStartDate] = useState(fiveYearsAgo);
  const [endDate, setEndDate] = useState(today);
  const [includeSpy, setIncludeSpy] = useState(true);
  const [includeReal, setIncludeReal] = useState(true);

  const createMut = useMutation({
    mutationFn: (args: { name: string; items: PortfolioItem[]; base_type: string; account_ids: string[] | null }) =>
      createPortfolio(args),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolios"] });
      setEditorOpen(false);
    },
    onError: () => toast("포트폴리오 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: (args: { id: string; name: string; items: PortfolioItem[]; base_type: string; account_ids: string[] | null }) =>
      updatePortfolio(args.id, { name: args.name, items: args.items, base_type: args.base_type, account_ids: args.account_ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolios"] });
      setEditingPortfolio(null);
      setEditorOpen(false);
      setAnalysis(null);
    },
    onError: () => toast("포트폴리오 수정에 실패했습니다"),
  });

  const deleteMut = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["portfolios"] });
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      setAnalysis(null);
      setBacktestResult(null);
    },
    onError: () => toast("포트폴리오 삭제에 실패했습니다"),
  });

  const runMut = useMutation({
    mutationFn: () =>
      runBacktest({
        portfolio_ids: Array.from(selectedIds),
        start_date: startDate,
        end_date: endDate,
        include_spy: includeSpy,
        include_real_portfolio: includeReal,
      }),
    onSuccess: (data) => setBacktestResult(data),
    onError: () => toast("백테스트 실행에 실패했습니다"),
  });

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  function handleSave(name: string, items: PortfolioItem[], baseType: string, accountIds: string[] | null) {
    if (editingPortfolio) {
      updateMut.mutate({ id: editingPortfolio.id, name, items, base_type: baseType, account_ids: accountIds });
    } else {
      createMut.mutate({ name, items, base_type: baseType, account_ids: accountIds });
    }
  }

  async function handleRebalancingAnalysis() {
    const [id] = Array.from(selectedIds);
    if (!id) return;
    setAnalysisMode("rebalancing");
    setBacktestResult(null);
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysis(null);
    try {
      // account_ids는 백엔드에서 portfolio.account_ids로 자동 처리
      const result = await analyzePortfolio(id);
      setAnalysis(result);
    } catch {
      setAnalysisError("분석 중 오류가 발생했습니다.");
    } finally {
      setAnalyzing(false);
    }
  }

  function handleSwitchToBacktest() {
    setAnalysisMode("backtest");
    setAnalysis(null);
    setAnalysisError(null);
  }

  const canRunBacktest =
    startDate < endDate && (selectedIds.size > 0 || includeSpy || includeReal);
  const canRebalance = selectedIds.size === 1;
  const saving = createMut.isPending || updateMut.isPending;

  const selectedNames = portfolios
    .filter((p) => selectedIds.has(p.id))
    .map((p) => p.name)
    .join(", ");

  // 포트폴리오에 지정된 계좌 이름을 표시하는 헬퍼
  function getAccountLabel(p: Portfolio): string {
    if (!p.account_ids?.length) return "모든 주식 계좌";
    const names = p.account_ids
      .map((id) => stockAccounts.find((a) => a.id === id)?.name ?? id.slice(0, 8))
      .filter(Boolean);
    return names.length <= 2 ? names.join(", ") : `${names.slice(0, 2).join(", ")} 외 ${names.length - 2}개`;
  }

  return (
    <div className="flex gap-6">
      {/* ── 좌측: 포트폴리오 목록 ──────────────────────────────────── */}
      <div className="w-72 flex-shrink-0 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">포트폴리오</h3>
          <button
            onClick={() => { setEditingPortfolio(null); setEditorOpen(true); }}
            className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors"
          >
            <Plus size={13} /> 새로 만들기
          </button>
        </div>

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 size={20} className="animate-spin text-gray-400 dark:text-gray-500" />
          </div>
        ) : portfolios.length === 0 ? (
          <div className="text-center py-10 text-sm text-gray-400 dark:text-gray-500">
            <div className="mb-2">포트폴리오가 없습니다.</div>
            <button
              onClick={() => { setEditingPortfolio(null); setEditorOpen(true); }}
              className="text-blue-600 dark:text-blue-400 hover:underline"
            >
              + 새로 만들기
            </button>
          </div>
        ) : (
          portfolios.map((p) => (
            <div
              key={p.id}
              className={`rounded-xl border p-3 cursor-pointer transition-colors ${
                selectedIds.has(p.id)
                  ? "border-blue-400 bg-blue-50 dark:bg-blue-950"
                  : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800"
              }`}
              onClick={() => toggleSelect(p.id)}
            >
              <div className="flex items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={selectedIds.has(p.id)}
                  onChange={() => toggleSelect(p.id)}
                  onClick={(e) => e.stopPropagation()}
                  className="mt-0.5 rounded text-blue-600 flex-shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-1">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                        {p.name}
                      </p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {p.base_type === "STOCK_ONLY" ? "주식 자산 기준" : "전체 자산 기준"} · {p.items.length}개 항목
                      </p>
                      {stockAccounts.length > 1 && (
                        <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
                          계좌: {getAccountLabel(p)}
                        </p>
                      )}
                    </div>
                    <div className="flex gap-0.5 shrink-0">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingPortfolio(p); setEditorOpen(true); }}
                        className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (confirm(`"${p.name}"을(를) 삭제하시겠습니까?`)) deleteMut.mutate(p.id);
                        }}
                        className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── 우측: 분석 패널 ──────────────────────────────────────── */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* 분석 버튼 행 */}
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={handleRebalancingAnalysis}
            disabled={!canRebalance || analyzing}
            title={!canRebalance ? "포트폴리오를 1개만 선택하세요" : undefined}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-40 ${
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
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              analysisMode === "backtest"
                ? "bg-blue-600 text-white hover:bg-blue-700"
                : "bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
            }`}
          >
            백테스팅
          </button>

          {selectedIds.size > 0 && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              {selectedNames}
              {selectedIds.size > 1 && ` 외 ${selectedIds.size - 1}개`} 선택됨
            </span>
          )}
        </div>

        {/* 백테스팅 설정 패널 */}
        {analysisMode === "backtest" && (
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
            <div className="flex flex-wrap gap-4 items-end">
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">시작일</label>
                <input
                  type="date"
                  value={startDate}
                  max={endDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 dark:text-gray-500 font-medium mb-1">종료일</label>
                <input
                  type="date"
                  value={endDate}
                  min={startDate}
                  max={today}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div className="flex items-center gap-4">
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
              </div>
              <button
                onClick={() => { setBacktestResult(null); runMut.mutate(); }}
                disabled={!canRunBacktest || runMut.isPending}
                className="ml-auto px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {runMut.isPending ? "계산 중..." : "▶ 백테스팅 실행"}
              </button>
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
            />
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

      {/* 포트폴리오 에디터 모달 */}
      {editorOpen && (
        <UnifiedPortfolioEditor
          initial={editingPortfolio}
          accounts={stockAccounts}
          onSave={handleSave}
          onClose={() => { setEditorOpen(false); setEditingPortfolio(null); }}
          saving={saving}
        />
      )}
    </div>
  );
}
