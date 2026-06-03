import { useMemo, useState } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Edit2, GripVertical, Loader2, Plus, Trash2 } from "lucide-react";
import {
  Portfolio,
  PortfolioItem,
  createPortfolio,
  deletePortfolio,
  fetchPortfolios,
  reorderPortfolios,
  updatePortfolio,
} from "../../api/portfolios";
import { fetchAccounts } from "../../api/assets";
import UnifiedPortfolioEditor from "./UnifiedPortfolioEditor";
import { AnalysisPanel } from "./AnalysisPanel";
import { toast } from "../../utils/toast";
import { invalidatePortfolioData } from "../../utils/queryInvalidation";
import { QUERY_KEYS } from "../../constants/queryKeys";
import { fetchRebalancingAlerts } from "../../api/alerts";
import ConfirmModal from "../common/ConfirmModal";
import RebalancingAlertModal from "./RebalancingAlertModal";
import { STALE_TIME } from "../../constants/queryConfig";

function SortablePortfolioItem({
  id,
  children,
}: {
  id: string;
  children: (props: { dragHandleListeners: React.HTMLAttributes<HTMLElement> }) => React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    position: "relative",
    zIndex: isDragging ? 1 : undefined,
  };
  return (
    <div ref={setNodeRef} style={style}>
      {children({ dragHandleListeners: { ...attributes, ...listeners } as React.HTMLAttributes<HTMLElement> })}
    </div>
  );
}

export default function PortfolioAnalysisTab() {
  const qc = useQueryClient();

  const { data: portfolios = [], isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });

  const [localOrder, setLocalOrder] = useState<string[]>([]);

  const sortedPortfolios = useMemo(() => {
    if (!localOrder.length || localOrder.length !== portfolios.length) return portfolios;
    const orderMap = new Map(localOrder.map((id, i) => [id, i]));
    return [...portfolios].sort((a, b) => (orderMap.get(a.id) ?? Infinity) - (orderMap.get(b.id) ?? Infinity));
  }, [portfolios, localOrder]);

  const { data: accounts = [] } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });
  const activeAccounts = accounts.filter((a) => a.is_active);
  const stockAccounts = activeAccounts.filter((a) =>
    ["STOCK_KIS", "STOCK_OTHER"].includes(a.asset_type)
  );

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [alertModalPortfolioId, setAlertModalPortfolioId] = useState<string | null>(null);

  const { data: rebalancingAlerts = [] } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const alertPortfolioIds = new Set(rebalancingAlerts.map((a) => a.portfolio_id));
  const alertByPortfolioId = Object.fromEntries(rebalancingAlerts.map((a) => [a.portfolio_id, a]));

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const currentIds = sortedPortfolios.map((p) => p.id);
    const oldIndex = currentIds.indexOf(active.id as string);
    const newIndex = currentIds.indexOf(over.id as string);
    const newOrder = arrayMove(currentIds, oldIndex, newIndex);

    setLocalOrder(newOrder);
    reorderPortfolios(newOrder.map((id, i) => ({ id, sort_order: i }))).catch(() => {
      setLocalOrder(currentIds);
      toast("순서 변경에 실패했습니다");
    });
  }

  const createMut = useMutation({
    mutationFn: (args: { name: string; items: PortfolioItem[]; base_type: string; account_ids: string[] | null }) =>
      createPortfolio(args),
    onSuccess: () => {
      invalidatePortfolioData(qc);
      setEditorOpen(false);
    },
    onError: () => toast("포트폴리오 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: (args: { id: string; name: string; items: PortfolioItem[]; base_type: string; account_ids: string[] | null }) =>
      updatePortfolio(args.id, { name: args.name, items: args.items, base_type: args.base_type, account_ids: args.account_ids }),
    onSuccess: () => {
      invalidatePortfolioData(qc);
      setEditingPortfolio(null);
      setEditorOpen(false);
    },
    onError: () => toast("포트폴리오 수정에 실패했습니다"),
  });

  const deleteMut = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: (_, id) => {
      invalidatePortfolioData(qc);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    },
    onError: () => toast("포트폴리오 삭제에 실패했습니다"),
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

  const saving = createMut.isPending || updateMut.isPending;

  const selectedNames = sortedPortfolios
    .filter((p) => selectedIds.has(p.id))
    .map((p) => p.name)
    .join(", ");

  // 포트폴리오에 지정된 계좌 이름 헬퍼
  function getAccountLabel(p: Portfolio): string {
    if (!p.account_ids?.length) return "모든 주식 계좌";
    const names = p.account_ids
      .map((id) => stockAccounts.find((a) => a.id === id)?.name ?? id.slice(0, 8))
      .filter(Boolean);
    return names.length <= 2 ? names.join(", ") : `${names.slice(0, 2).join(", ")} 외 ${names.length - 2}개`;
  }

  return (
    <div className="flex flex-col md:flex-row gap-4 md:gap-6">
      {/* ── 포트폴리오 목록 (모바일: 상단 전체폭, 데스크톱: 좌측 고정) ── */}
      <div className="w-full md:w-72 lg:w-80 md:flex-shrink-0 space-y-3">
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
        ) : sortedPortfolios.length === 0 ? (
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
          <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
            <SortableContext items={sortedPortfolios.map((p) => p.id)} strategy={verticalListSortingStrategy}>
              {sortedPortfolios.map((p) => (
                <SortablePortfolioItem key={p.id} id={p.id}>
                  {({ dragHandleListeners }) => (
                    <div
                      className={`rounded-xl border p-3.5 cursor-pointer transition-colors ${
                        selectedIds.has(p.id)
                          ? "border-blue-400 bg-blue-50 dark:bg-blue-950"
                          : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800"
                      }`}
                      onClick={() => toggleSelect(p.id)}
                    >
                      <div className="flex items-start gap-2">
                        <button
                          {...dragHandleListeners}
                          onClick={(e) => e.stopPropagation()}
                          className="mt-0.5 text-gray-300 dark:text-gray-600 hover:text-gray-500 dark:hover:text-gray-400 cursor-grab active:cursor-grabbing flex-shrink-0 touch-none"
                        >
                          <GripVertical size={14} />
                        </button>
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
                              <p className="text-sm font-semibold text-gray-800 dark:text-gray-200 truncate">
                                {p.name}
                              </p>
                              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 truncate">
                                {p.base_type === "STOCK_ONLY" ? "주식 기준" : "전체 자산"} · {p.items.length}개 항목
                                {stockAccounts.length > 1 && ` · ${getAccountLabel(p)}`}
                              </p>
                              {/* 미니 비중 바 */}
                              {p.items.length > 0 && (() => {
                                const MINI_COLORS = ["#2563EB","#16A34A","#D97706","#DC2626","#7C3AED","#0891B2","#DB2777","#059669"];
                                const sorted = [...p.items].sort((a, b) => b.weight - a.weight);
                                const top = sorted.slice(0, 5);
                                const rest = sorted.slice(5).reduce((s, i) => s + i.weight, 0);
                                return (
                                  <div className="mt-1.5 flex h-2 rounded-full overflow-hidden gap-px">
                                    {top.map((item, ci) => (
                                      <div
                                        key={item.ticker}
                                        title={`${item.name ?? item.ticker}: ${item.weight.toFixed(1)}%`}
                                        style={{ width: `${item.weight}%`, backgroundColor: MINI_COLORS[ci] }}
                                      />
                                    ))}
                                    {rest > 0 && (
                                      <div
                                        title={`기타: ${rest.toFixed(1)}%`}
                                        style={{ width: `${rest}%`, backgroundColor: "#9CA3AF" }}
                                      />
                                    )}
                                  </div>
                                );
                              })()}
                            </div>
                            <div className="flex gap-0.5 shrink-0 items-center">
                              {alertPortfolioIds.has(p.id) && (
                                <span
                                  className={`text-xs px-1.5 py-0.5 rounded-full font-medium mr-0.5 ${
                                    alertByPortfolioId[p.id]?.mode === "AUTO"
                                      ? "bg-orange-100 dark:bg-orange-950 text-orange-700 dark:text-orange-400"
                                      : "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400"
                                  }`}
                                >
                                  {alertByPortfolioId[p.id]?.mode === "AUTO" ? "자동" : "알림"}
                                </span>
                              )}
                              <button
                                onClick={(e) => { e.stopPropagation(); setEditingPortfolio(p); setEditorOpen(true); }}
                                className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors"
                              >
                                <Edit2 size={13} />
                              </button>
                              <button
                                onClick={(e) => { e.stopPropagation(); setAlertModalPortfolioId(p.id); }}
                                className={`p-1.5 rounded-lg transition-colors ${
                                  alertPortfolioIds.has(p.id)
                                    ? "text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950"
                                    : "text-gray-300 dark:text-gray-600 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950"
                                }`}
                                title="리밸런싱 알림 설정"
                              >
                                <Bell size={13} />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setConfirmDeleteId(p.id);
                                }}
                                className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </SortablePortfolioItem>
              ))}
            </SortableContext>
          </DndContext>
        )}
      </div>

      {/* ── 우측: 분석 패널 ──────────────────────────────────────── */}
      <AnalysisPanel
        selectedIds={selectedIds}
        selectedNames={selectedNames}
        portfolios={sortedPortfolios}
        activeAccounts={activeAccounts}
        onOpenAlertModal={setAlertModalPortfolioId}
      />
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
      {confirmDeleteId && (
        <ConfirmModal
          message="포트폴리오를 삭제하시겠습니까?"
          confirmLabel="삭제"
          onConfirm={() => { deleteMut.mutate(confirmDeleteId); setConfirmDeleteId(null); }}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}
      {alertModalPortfolioId && (
        <RebalancingAlertModal
          key={alertModalPortfolioId}
          portfolioId={alertModalPortfolioId}
          portfolioName={sortedPortfolios.find((p) => p.id === alertModalPortfolioId)?.name ?? ""}
          onClose={() => setAlertModalPortfolioId(null)}
        />
      )}
    </div>
  );
}
