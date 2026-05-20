import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { BacktestResult, runBacktest } from "../../api/backtest";
import {
  Portfolio,
  PortfolioItem,
  createPortfolio,
  deletePortfolio,
  fetchPortfolios,
  updatePortfolio,
} from "../../api/portfolios";
import UnifiedPortfolioEditor from "../portfolios/UnifiedPortfolioEditor";
import BacktestResultChart from "./BacktestResultChart";
import BacktestMetricsTable from "./BacktestMetricsTable";
import { toast } from "../../utils/toast";

const today = new Date().toISOString().slice(0, 10);
const fiveYearsAgo = `${new Date().getFullYear() - 5}-01-01`;

const SKIP_TICKERS = new Set(["CASH", "REAL_ESTATE"]);
const SKIP_MARKETS = new Set(["KR_PROPERTY"]);

function investableItems(items: PortfolioItem[]) {
  return items.filter((i) => !SKIP_TICKERS.has(i.ticker) && !SKIP_MARKETS.has(i.market));
}

export default function BacktestTab() {
  const qc = useQueryClient();

  // ── 포트폴리오 목록 ─────────────────────────────────────
  const { data: portfolios = [], isLoading: listLoading } = useQuery({
    queryKey: ["portfolios"],
    queryFn: fetchPortfolios,
  });

  const [editorOpen, setEditorOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Portfolio | null>(null);

  const createMut = useMutation({
    mutationFn: (args: { name: string; items: PortfolioItem[]; base_type: string }) =>
      createPortfolio(args),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["portfolios"] }); setEditorOpen(false); },
    onError: () => toast("포트폴리오 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: (args: { id: string; name: string; items: PortfolioItem[]; base_type: string }) =>
      updatePortfolio(args.id, { name: args.name, items: args.items, base_type: args.base_type }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["portfolios"] }); setEditTarget(null); },
    onError: () => toast("포트폴리오 수정에 실패했습니다"),
  });

  const deleteMut = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portfolios"] }),
    onError: () => toast("포트폴리오 삭제에 실패했습니다"),
  });

  // ── 백테스팅 실행 설정 ──────────────────────────────────
  const [startDate, setStartDate] = useState(fiveYearsAgo);
  const [endDate, setEndDate] = useState(today);
  const [includeSpy, setIncludeSpy] = useState(true);
  const [includeReal, setIncludeReal] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const [result, setResult] = useState<BacktestResult | null>(null);

  const runMut = useMutation({
    mutationFn: () =>
      runBacktest({
        portfolio_ids: Array.from(selectedIds),
        start_date: startDate,
        end_date: endDate,
        include_spy: includeSpy,
        include_real_portfolio: includeReal,
      }),
    onSuccess: (data) => setResult(data),
    onError: () => toast("백테스트 실행에 실패했습니다"),
  });

  const canRun =
    startDate < endDate &&
    (selectedIds.size > 0 || includeSpy || includeReal);

  return (
    <div className="space-y-6">
      {/* ── 저장된 포트폴리오 목록 ─────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">저장된 포트폴리오</h2>
          <button
            onClick={() => setEditorOpen(true)}
            className="flex items-center gap-1.5 text-sm bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus size={14} /> 새 포트폴리오
          </button>
        </div>

        {listLoading ? (
          <div className="py-4 text-center text-sm text-gray-300 dark:text-gray-600">로딩 중...</div>
        ) : portfolios.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-300 dark:text-gray-600">
            아직 저장된 포트폴리오가 없습니다. 새 포트폴리오를 추가해보세요.
          </p>
        ) : (
          <div className="space-y-2">
            {portfolios.map((p) => {
              const investable = investableItems(p.items);
              const skipped = p.items.length - investable.length;
              return (
                <div
                  key={p.id}
                  className={`flex items-center justify-between p-3 rounded-xl border cursor-pointer transition-colors ${
                    selectedIds.has(p.id)
                      ? "border-blue-400 bg-blue-50 dark:bg-blue-950"
                      : "border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
                  }`}
                  onClick={() => toggleSelect(p.id)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(p.id)}
                      onChange={() => toggleSelect(p.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded text-blue-600"
                    />
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-800 dark:text-gray-200">{p.name}</p>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {investable.map((h) => `${h.ticker} ${h.weight}%`).join(" · ")}
                        {skipped > 0 && (
                          <span className="text-gray-300 dark:text-gray-600 ml-1">(현금·부동산 제외)</span>
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0 ml-3">
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditTarget(p); }}
                      className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors"
                    >
                      <Pencil size={13} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteMut.mutate(p.id); }}
                      className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── 백테스팅 실행 패널 ────────────────────────────── */}
      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200 mb-4">백테스팅 실행</h2>

        <div className="flex flex-wrap gap-4 items-end">
          {/* 기간 */}
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

          {/* 벤치마크 체크박스 */}
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
            onClick={() => runMut.mutate()}
            disabled={!canRun || runMut.isPending}
            className="ml-auto px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {runMut.isPending ? "계산 중..." : "▶ 백테스팅 실행"}
          </button>
        </div>

        {selectedIds.size > 0 && (
          <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
            선택된 포트폴리오: {portfolios.filter((p) => selectedIds.has(p.id)).map((p) => p.name).join(", ")}
          </p>
        )}

        {runMut.isError && (
          <p className="mt-2 text-xs text-red-500">백테스팅 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.</p>
        )}
      </div>

      {/* ── 결과 차트 + 지표 ─────────────────────────────── */}
      {result && result.dates.length > 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 space-y-6">
          <BacktestResultChart dates={result.dates} series={result.series} />
          <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
            <BacktestMetricsTable metrics={result.metrics} />
          </div>
        </div>
      )}

      {result && result.dates.length === 0 && (
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 text-center text-sm text-gray-300 dark:text-gray-600 py-8">
          해당 기간의 가격 데이터가 없습니다. 기간을 조정해보세요.
        </div>
      )}

      {/* ── 모달 ────────────────────────────────────────── */}
      {editorOpen && (
        <UnifiedPortfolioEditor
          onSave={(name, items, baseType) => createMut.mutate({ name, items, base_type: baseType })}
          onClose={() => setEditorOpen(false)}
          saving={createMut.isPending}
        />
      )}
      {editTarget && (
        <UnifiedPortfolioEditor
          initial={editTarget}
          onSave={(name, items, baseType) =>
            updateMut.mutate({ id: editTarget.id, name, items, base_type: baseType })
          }
          onClose={() => setEditTarget(null)}
          saving={updateMut.isPending}
        />
      )}
    </div>
  );
}
