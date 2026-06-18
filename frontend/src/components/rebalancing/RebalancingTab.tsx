import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit2, History, Loader2, Plus, RefreshCw, Trash2 } from "lucide-react";
import { analyzePortfolio, ExecutionResult, RebalancingAnalysis } from "@/api/rebalancing";
import {
  createPortfolio,
  deletePortfolio,
  fetchPortfolios,
  Portfolio,
  PortfolioItem,
  updatePortfolio,
} from "@/api/portfolios";
import { fetchAccounts } from "@/api/assets";
import UnifiedPortfolioEditor from "@/components/portfolio-analysis/UnifiedPortfolioEditor";
import RebalancingTable from "./RebalancingTable";
import RebalancingHistoryTab from "./RebalancingHistoryTab";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData } from "@/utils/queryInvalidation";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import ConfirmModal from "@/components/common/ConfirmModal";
import { fetchMarketSignal } from "@/api/marketSignals";
import MarketSignalBanner from "./MarketSignalBanner";

function applyExecutionResults(
  analysis: RebalancingAnalysis,
  results: ExecutionResult[],
): RebalancingAnalysis {
  const successMap: Record<string, number> = {};
  for (const result of results) {
    for (const order of result.orders) {
      if (order.status === "SUCCESS") {
        const delta = order.side === "BUY" ? order.quantity : -order.quantity;
        successMap[order.ticker] = (successMap[order.ticker] ?? 0) + delta;
      }
    }
  }
  return {
    ...analysis,
    items: analysis.items.map((item) => {
      const delta = successMap[item.ticker];
      if (delta === undefined || item.shares_to_trade === null) return item;
      const newShares = item.shares_to_trade - delta;
      const rounded = Math.abs(newShares) < 0.5 ? 0 : newShares;
      return {
        ...item,
        shares_to_trade: rounded,
        diff_krw: item.current_price_krw != null ? rounded * item.current_price_krw : item.diff_krw,
      };
    }),
  };
}

type TabType = "analysis" | "history";

export default function RebalancingTab() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<TabType>("analysis");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<RebalancingAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [includeCash, setIncludeCash] = useState(false);

  const adjustedAnalysis = useMemo(() => {
    if (!analysis || !includeCash) return analysis;
    const cash = analysis.available_cash_krw ?? 0;
    if (cash <= 0) return analysis;
    const cashBase = analysis.base_value_krw + cash;
    const items = analysis.items.map((item) => {
      const newTarget = cashBase * (item.target_weight_pct / 100);
      const newCurrentPct = cashBase > 0 ? (item.current_value_krw / cashBase) * 100 : 0;
      const newDiff = newTarget - item.current_value_krw;
      const newShares =
        item.current_price_krw && item.current_price_krw > 0
          ? Math.round(newDiff / item.current_price_krw)
          : item.shares_to_trade;
      return {
        ...item,
        target_value_krw: newTarget,
        current_weight_pct: newCurrentPct,
        weight_diff_pct: item.target_weight_pct - newCurrentPct,
        diff_krw: newDiff,
        shares_to_trade: newShares,
      };
    });
    return { ...analysis, base_value_krw: cashBase, items };
  }, [analysis, includeCash]);

  const { data: portfolios = [], isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });
  // fetchAccounts는 is_active=True 필터로 활성 계좌만 반환
  const allAccounts = accounts;

  const { data: marketSignal } = useQuery({
    queryKey: QUERY_KEYS.marketSignal,
    queryFn: fetchMarketSignal,
    staleTime: STALE_TIME.LONG,
  });

  const createMutation = useMutation({
    mutationFn: (body: { name: string; items: PortfolioItem[]; base_type: string }) =>
      createPortfolio(body),
    onSuccess: () => {
      invalidatePortfolioData(queryClient);
      setEditorOpen(false);
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 저장에 실패했습니다"), "error"),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: { name?: string; items?: PortfolioItem[]; base_type?: string };
    }) => updatePortfolio(id, body),
    onSuccess: () => {
      invalidatePortfolioData(queryClient);
      setEditorOpen(false);
      setEditingPortfolio(null);
      setAnalysis(null);
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 수정에 실패했습니다"), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deletePortfolio(id),
    onSuccess: (_, id) => {
      invalidatePortfolioData(queryClient);
      if (selectedId === id) {
        setSelectedId(null);
        setAnalysis(null);
      }
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 삭제에 실패했습니다"), "error"),
  });

  function handleSave(name: string, items: PortfolioItem[], baseType: string) {
    if (editingPortfolio) {
      updateMutation.mutate({
        id: editingPortfolio.id,
        body: { name, items, base_type: baseType },
      });
    } else {
      createMutation.mutate({ name, items, base_type: baseType });
    }
  }

  function handleExecuted(results: ExecutionResult[]) {
    setAnalysis((prev) => (prev ? applyExecutionResults(prev, results) : prev));
  }

  async function handleAnalyze(portfolioId: string) {
    setSelectedId(portfolioId);
    setAnalyzing(true);
    setAnalysisError(null);
    setAnalysis(null);
    setIncludeCash(false);
    try {
      const result = await analyzePortfolio(portfolioId);
      setAnalysis(result);
    } catch {
      setAnalysisError("분석 중 오류가 발생했습니다.");
    } finally {
      setAnalyzing(false);
    }
  }

  function openCreate() {
    setEditingPortfolio(null);
    setEditorOpen(true);
  }

  function openEdit(p: Portfolio) {
    setEditingPortfolio(p);
    setEditorOpen(true);
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="space-y-4">
      {/* 탭 */}
      <div className="flex gap-1 border-b border-gray-700">
        <button
          onClick={() => setActiveTab("analysis")}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "analysis"
              ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          <RefreshCw size={14} /> 분석 및 실행
        </button>
        <button
          onClick={() => setActiveTab("history")}
          className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === "history"
              ? "text-blue-400 border-b-2 border-blue-400 -mb-px"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          <History size={14} /> 실행 이력
        </button>
      </div>

      {activeTab === "history" && <RebalancingHistoryTab />}

      {activeTab === "analysis" && (
        <div className="flex gap-6">
          {/* 좌측: 포트폴리오 목록 */}
          <div className="w-72 flex-shrink-0 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-300">목표 포트폴리오</h3>
              <button
                onClick={openCreate}
                className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-gray-700 transition-colors"
              >
                <Plus size={13} /> 새로 만들기
              </button>
            </div>

            {isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 size={20} className="animate-spin text-gray-500" />
              </div>
            ) : portfolios.length === 0 ? (
              <div className="text-center py-10 text-sm text-gray-500">
                <div className="mb-2">포트폴리오가 없습니다.</div>
                <button onClick={openCreate} className="text-blue-400 hover:underline">
                  + 새로 만들기
                </button>
              </div>
            ) : (
              portfolios.map((p) => (
                <div
                  key={p.id}
                  className={`bg-gray-800 rounded-xl border p-4 cursor-pointer transition-colors ${
                    selectedId === p.id
                      ? "border-blue-500 bg-gray-700"
                      : "border-gray-700 hover:border-gray-600"
                  }`}
                  onClick={() => setSelectedId(p.id)}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="text-sm font-medium text-gray-100">{p.name}</div>
                      <div className="text-xs text-gray-500 mt-0.5">
                        {p.base_type === "STOCK_ONLY" ? "주식 자산 기준" : "전체 자산 기준"}
                      </div>
                    </div>
                    <div className="flex gap-1 ml-2">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          openEdit(p);
                        }}
                        aria-label="포트폴리오 수정"
                        className="p-1 text-gray-500 hover:text-blue-400 hover:bg-gray-700 rounded transition-colors"
                      >
                        <Edit2 size={13} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setConfirmDeleteId(p.id);
                        }}
                        aria-label="포트폴리오 삭제"
                        className="p-1 text-gray-500 hover:text-red-400 hover:bg-gray-700 rounded transition-colors"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </div>

                  <div className="text-xs text-gray-400 mb-3">{p.items.length}개 항목</div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleAnalyze(p.id);
                    }}
                    disabled={analyzing && selectedId === p.id}
                    className="w-full flex items-center justify-center gap-1 bg-blue-600 text-white text-xs py-1.5 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                  >
                    {analyzing && selectedId === p.id ? (
                      <>
                        <Loader2 size={12} className="animate-spin" /> 분석 중...
                      </>
                    ) : (
                      <>
                        <RefreshCw size={12} /> 리밸런싱 분석
                      </>
                    )}
                  </button>
                </div>
              ))
            )}
          </div>

          {/* 우측: 분석 결과 */}
          <div className="flex-1 min-w-0">
            {analysis ? (
              <div className="bg-gray-800 rounded-2xl border border-gray-700 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-gray-100">
                    {analysis.portfolio_name} — 리밸런싱 분석
                  </h3>
                  <button
                    onClick={() => handleAnalyze(analysis.portfolio_id)}
                    disabled={analyzing}
                    className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 px-2 py-1 rounded-lg hover:bg-gray-700 transition-colors"
                  >
                    <RefreshCw size={12} /> 다시 분석
                  </button>
                </div>
                {marketSignal && <MarketSignalBanner signal={marketSignal} />}
                <RebalancingTable
                  analysis={adjustedAnalysis ?? analysis}
                  portfolioId={analysis.portfolio_id}
                  accounts={allAccounts}
                  onExecuted={handleExecuted}
                  includeCash={includeCash}
                  onToggleCash={setIncludeCash}
                />
              </div>
            ) : analysisError ? (
              <div className="flex items-center justify-center h-48 text-sm text-red-500">
                {analysisError}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-center text-gray-400">
                <div className="text-4xl mb-3">⚖️</div>
                <div className="text-sm font-medium mb-1">포트폴리오를 선택하고 분석하세요</div>
                <div className="text-xs">
                  목표 비중과 현재 자산을 비교해 매수/매도 금액을 알려드립니다
                </div>
              </div>
            )}
          </div>

          {/* 에디터 모달 */}
          {editorOpen && (
            <UnifiedPortfolioEditor
              initial={editingPortfolio}
              onSave={handleSave}
              onClose={() => {
                setEditorOpen(false);
                setEditingPortfolio(null);
              }}
              saving={saving}
            />
          )}
          {confirmDeleteId && (
            <ConfirmModal
              message="포트폴리오를 삭제하시겠습니까?"
              confirmLabel="삭제"
              onConfirm={() => {
                deleteMutation.mutate(confirmDeleteId);
                setConfirmDeleteId(null);
              }}
              onCancel={() => setConfirmDeleteId(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
