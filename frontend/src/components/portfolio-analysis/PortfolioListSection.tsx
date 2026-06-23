import { useRef } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  AlertCircle,
  AlertTriangle,
  Bell,
  CheckCircle,
  Edit2,
  GripVertical,
  Loader2,
  Plus,
  RefreshCw,
  Target,
  Trash2,
} from "lucide-react";
import { Portfolio } from "@/api/portfolios";
import { RebalancingAlert } from "@/api/alerts";
import { AssetAccount } from "@/api/assets";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { toast } from "@/utils/toast";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";

function SortablePortfolioItem({
  id,
  children,
}: {
  id: string;
  children: (props: { dragHandleListeners: React.HTMLAttributes<HTMLElement> }) => React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    position: "relative",
    zIndex: isDragging ? 1 : undefined,
  };
  return (
    <div ref={setNodeRef} style={style}>
      {children({
        dragHandleListeners: { ...attributes, ...listeners } as React.HTMLAttributes<HTMLElement>,
      })}
    </div>
  );
}

interface PortfolioListSectionProps {
  portfolios: Portfolio[];
  isLoading: boolean;
  selectedIds: Set<string>;
  stockAccounts: AssetAccount[];
  alertPortfolioIds: Set<string>;
  alertByPortfolioId: Record<string, RebalancingAlert>;
  driftByPortfolioId?: Record<string, PortfolioDriftSummary>;
  isTargetPending: boolean;
  onDragEnd: (event: DragEndEvent) => void;
  onToggleSelect: (id: string) => void;
  onOpenEditor: (portfolio: Portfolio | null) => void;
  onOpenAlertModal: (portfolioId: string) => void;
  onConfirmDelete: (portfolioId: string) => void;
  onBatchSetTarget: (portfolioId: string | null, accountIds: string[]) => void;
  onRefresh?: () => Promise<void>;
}

export default function PortfolioListSection({
  portfolios,
  isLoading,
  selectedIds,
  stockAccounts,
  alertPortfolioIds,
  alertByPortfolioId,
  driftByPortfolioId,
  isTargetPending,
  onDragEnd,
  onToggleSelect,
  onOpenEditor,
  onOpenAlertModal,
  onConfirmDelete,
  onBatchSetTarget,
  onRefresh,
}: PortfolioListSectionProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { isPulling, pullDistance, isRefreshing } = usePullToRefresh({
    onRefresh: onRefresh ?? (() => Promise.resolve()),
    containerRef,
    disabled: !onRefresh,
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
  );

  const unassignedAccounts = stockAccounts.filter((a) => !a.target_portfolio_id);

  function getPortfolioTargetState(p: Portfolio): "full" | "partial" | "none" {
    const linkedIds = p.account_ids?.length ? p.account_ids : stockAccounts.map((a) => a.id);
    const relevant = stockAccounts.filter((a) => linkedIds.includes(a.id));
    if (relevant.length === 0) return "none";
    const assigned = relevant.filter((a) => a.target_portfolio_id === p.id).length;
    if (assigned === 0) return "none";
    return assigned === relevant.length ? "full" : "partial";
  }

  function getAccountLabel(p: Portfolio): string {
    if (!p.account_ids?.length) return "모든 주식 계좌";
    const names = p.account_ids
      .map((id) => stockAccounts.find((a) => a.id === id)?.name ?? id.slice(0, 8))
      .filter(Boolean);
    return names.length <= 2
      ? names.join(", ")
      : `${names.slice(0, 2).join(", ")} 외 ${names.length - 2}개`;
  }

  function handleToggleTarget(e: React.MouseEvent, p: Portfolio) {
    e.stopPropagation();
    const linkedIds = p.account_ids?.length ? p.account_ids : stockAccounts.map((a) => a.id);
    const relevant = stockAccounts.filter((a) => linkedIds.includes(a.id));
    if (relevant.length === 0) return;
    const currentState = getPortfolioTargetState(p);
    if (currentState === "full") {
      onBatchSetTarget(
        null,
        relevant.map((a) => a.id),
      );
      return;
    }
    const conflicting = relevant.filter(
      (a) => a.target_portfolio_id !== null && a.target_portfolio_id !== p.id,
    );
    if (conflicting.length > 0) {
      const conflictNames = conflicting
        .map((a) => {
          const targetPName =
            portfolios.find((po) => po.id === a.target_portfolio_id)?.name ?? "다른 포트폴리오";
          return `${a.name}(→${targetPName})`;
        })
        .join(", ");
      toast(
        `다음 계좌가 이미 다른 포트폴리오를 목표로 지정하고 있습니다: ${conflictNames}`,
        "error",
      );
      return;
    }
    onBatchSetTarget(
      p.id,
      relevant.map((a) => a.id),
    );
  }

  return (
    <div
      ref={containerRef}
      className="w-full md:w-72 lg:w-80 md:flex-shrink-0 space-y-3 overflow-y-auto"
    >
      {/* 당겨서 새로고침 인디케이터 */}
      {(isPulling || isRefreshing) && (
        <div
          className="flex items-center justify-center gap-1.5 text-xs text-gray-400 dark:text-gray-500 transition-all"
          style={{ height: isPulling ? `${pullDistance}px` : undefined }}
        >
          <RefreshCw
            size={14}
            className={isRefreshing ? "animate-spin" : ""}
            style={
              isPulling && !isRefreshing
                ? { transform: `rotate(${pullDistance * 3}deg)` }
                : undefined
            }
          />
          {isRefreshing ? "새로고침 중..." : "놓아서 새로고침"}
        </div>
      )}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">포트폴리오</h3>
        <button
          onClick={() => onOpenEditor(null)}
          className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors"
        >
          <Plus size={13} /> 새로 만들기
        </button>
      </div>

      {unassignedAccounts.length > 0 && portfolios.length > 0 && (
        <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <AlertCircle size={13} className="text-amber-500 flex-shrink-0" />
            <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
              목표 미지정 계좌
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            {unassignedAccounts.map((a) => (
              <span
                key={a.id}
                className="text-xs px-1.5 py-0.5 rounded-md bg-white dark:bg-gray-900 border border-amber-200 dark:border-amber-700 text-amber-700 dark:text-amber-400"
              >
                {a.name}
              </span>
            ))}
          </div>
          <p className="text-xs text-amber-600/70 dark:text-amber-500/70 mt-1.5">
            포트폴리오 카드에서 목표 지정 버튼을 클릭해 지정하세요.
          </p>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 size={20} className="animate-spin text-gray-400 dark:text-gray-500" />
        </div>
      ) : portfolios.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 dark:border-gray-700 p-5 text-center space-y-4">
          <div className="text-2xl">🎯</div>
          <div>
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
              목표 포트폴리오를 만들어 보세요
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              종목과 목표 비중을 설정하면 현재 보유 현황과 비교해 리밸런싱 가이드를 제공합니다.
            </p>
          </div>
          <div className="flex flex-col gap-1.5 text-left">
            {(["① 종목·비중 입력", "② 리밸런싱 분석 확인", "③ 이메일 알림 설정"] as const).map(
              (step) => (
                <div
                  key={step}
                  className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-300 dark:bg-blue-700 flex-shrink-0" />
                  {step}
                </div>
              ),
            )}
          </div>
          <button
            onClick={() => onOpenEditor(null)}
            className="w-full py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            첫 번째 포트폴리오 만들기
          </button>
        </div>
      ) : (
        <DndContext sensors={sensors} onDragEnd={onDragEnd}>
          <SortableContext
            items={portfolios.map((p) => p.id)}
            strategy={verticalListSortingStrategy}
          >
            {portfolios.map((p) => {
              const tState = getPortfolioTargetState(p);
              return (
                <SortablePortfolioItem key={p.id} id={p.id}>
                  {({ dragHandleListeners }) => (
                    <div
                      className={`rounded-xl border p-3.5 cursor-pointer transition-colors ${
                        selectedIds.has(p.id)
                          ? "border-blue-400 bg-blue-50 dark:bg-blue-950"
                          : tState === "full"
                            ? "border-blue-200 dark:border-blue-700 bg-white dark:bg-gray-900 hover:bg-blue-50/50 dark:hover:bg-blue-950/40"
                            : tState === "partial"
                              ? "border-amber-200 dark:border-amber-700 bg-white dark:bg-gray-900 hover:bg-amber-50/50 dark:hover:bg-amber-950/40"
                              : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 hover:bg-gray-50 dark:hover:bg-gray-800"
                      }`}
                      onClick={() => onToggleSelect(p.id)}
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
                          onChange={() => onToggleSelect(p.id)}
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
                                {p.base_type === "STOCK_ONLY" ? "주식 기준" : "전체 자산"} ·{" "}
                                {p.items.length}개 항목
                                {stockAccounts.length > 1 && ` · ${getAccountLabel(p)}`}
                              </p>
                              {p.items.length > 0 &&
                                (() => {
                                  const MINI_COLORS = [
                                    "#2563EB",
                                    "#16A34A",
                                    "#D97706",
                                    "#DC2626",
                                    "#7C3AED",
                                    "#0891B2",
                                    "#DB2777",
                                    "#059669",
                                  ];
                                  const sorted = [...p.items].sort((a, b) => b.weight - a.weight);
                                  const top = sorted.slice(0, 5);
                                  const rest = sorted.slice(5).reduce((s, i) => s + i.weight, 0);
                                  return (
                                    <div className="mt-1.5 flex h-2 rounded-full overflow-hidden gap-px">
                                      {top.map((item, ci) => (
                                        <div
                                          key={item.ticker}
                                          title={`${item.name ?? item.ticker}: ${item.weight.toFixed(1)}%`}
                                          style={{
                                            width: `${item.weight}%`,
                                            backgroundColor: MINI_COLORS[ci],
                                          }}
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
                              {(() => {
                                const drift = driftByPortfolioId?.[p.id];
                                if (!drift) return null;
                                const isNeeded = drift.needs_rebalancing;
                                const isCaution = !isNeeded && drift.max_drift_pct >= drift.threshold_pct / 2;
                                if (isNeeded) return (
                                  <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium mr-0.5 bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-400">
                                    <AlertTriangle size={10} />
                                    {drift.max_drift_pct.toFixed(1)}% 이탈
                                  </span>
                                );
                                if (isCaution) return (
                                  <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium mr-0.5 bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-400">
                                    <AlertTriangle size={10} />
                                    {drift.max_drift_pct.toFixed(1)}% 주의
                                  </span>
                                );
                                return (
                                  <span className="flex items-center gap-0.5 text-xs px-1.5 py-0.5 rounded-full font-medium mr-0.5 bg-green-100 dark:bg-green-950/60 text-green-700 dark:text-green-400">
                                    <CheckCircle size={10} />
                                    안정
                                  </span>
                                );
                              })()}
                              {tState !== "none" && (
                                <span
                                  className={`text-xs px-1.5 py-0.5 rounded-full font-medium mr-0.5 ${
                                    tState === "full"
                                      ? "bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-400"
                                      : "bg-amber-100 dark:bg-amber-950 text-amber-700 dark:text-amber-400"
                                  }`}
                                >
                                  {tState === "full" ? "목표" : "일부"}
                                </span>
                              )}
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
                                onClick={(e) => handleToggleTarget(e, p)}
                                disabled={isTargetPending}
                                aria-label="목표 포트폴리오 지정"
                                title={
                                  tState === "full"
                                    ? "목표 지정 해제"
                                    : "이 포트폴리오를 목표로 지정"
                                }
                                className={`flex items-center gap-0.5 px-1.5 py-1 rounded-lg transition-colors text-xs ${
                                  tState === "full"
                                    ? "text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950"
                                    : tState === "partial"
                                      ? "text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950"
                                      : "text-gray-400 dark:text-gray-500 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950"
                                }`}
                              >
                                <Target size={12} />
                                {tState === "none" && <span>목표 지정</span>}
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onOpenEditor(p);
                                }}
                                aria-label="포트폴리오 수정"
                                className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors"
                              >
                                <Edit2 size={13} />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onOpenAlertModal(p.id);
                                }}
                                className={`p-1.5 rounded-lg transition-colors ${
                                  alertPortfolioIds.has(p.id)
                                    ? "text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950"
                                    : "text-gray-300 dark:text-gray-600 hover:text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950"
                                }`}
                                title="리밸런싱 알림 설정"
                                aria-label="리밸런싱 알림 설정"
                              >
                                <Bell size={13} />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  onConfirmDelete(p.id);
                                }}
                                aria-label="포트폴리오 삭제"
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
              );
            })}
          </SortableContext>
        </DndContext>
      )}
    </div>
  );
}
