import { useState } from "react";
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
import { ArrowLeftRight, CircleAlert, Loader2, Plus, Target } from "lucide-react";
import { Portfolio } from "@/api/portfolios";
import { RebalancingAlert } from "@/api/alerts";
import { AssetAccount } from "@/api/assets";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { getPortfolioTargetState } from "@/utils/portfolio";
import ConfirmModal from "@/components/common/ConfirmModal";
import Modal, { ModalBody } from "@/components/common/Modal";
import { useIsSmUp } from "@/hooks/useMediaQuery";
import { TOUCH_HEIGHT_MIN, TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";
import PortfolioCard from "./PortfolioCard";

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
  autoAlertCount: number;
  alertByPortfolioId: Record<string, RebalancingAlert>;
  driftByPortfolioId?: Record<string, PortfolioDriftSummary>;
  isTargetPending: boolean;
  onDragEnd: (event: DragEndEvent) => void;
  onToggleSelect: (id: string) => void;
  onOpenEditor: (portfolio: Portfolio | null) => void;
  onOpenAlertModal: (portfolioId: string) => void;
  onConfirmDelete: (portfolioId: string) => void;
  onBatchSetTarget: (portfolioId: string | null, accountIds: string[]) => void;
}

export default function PortfolioListSection({
  portfolios,
  isLoading,
  selectedIds,
  stockAccounts,
  alertPortfolioIds,
  autoAlertCount,
  alertByPortfolioId,
  driftByPortfolioId,
  isTargetPending,
  onDragEnd,
  onToggleSelect,
  onOpenEditor,
  onOpenAlertModal,
  onConfirmDelete,
  onBatchSetTarget,
}: PortfolioListSectionProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
  );

  const [pendingReassign, setPendingReassign] = useState<{
    portfolio: Portfolio;
    accountIds: string[];
    conflicts: { accountName: string; fromPortfolioName: string }[];
  } | null>(null);

  const isSmUp = useIsSmUp();
  const [sheetOpen, setSheetOpen] = useState(false);

  const unassignedAccounts = stockAccounts.filter((a) => !a.target_portfolio_id);

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
    const currentState = getPortfolioTargetState(p, stockAccounts);
    if (currentState === "full" || currentState === "partial") {
      const currentlyTargeted = stockAccounts.filter((a) => a.target_portfolio_id === p.id);
      onBatchSetTarget(
        null,
        currentlyTargeted.map((a) => a.id),
      );
      return;
    }
    const conflicting = relevant.filter(
      (a) => a.target_portfolio_id !== null && a.target_portfolio_id !== p.id,
    );
    if (conflicting.length > 0) {
      setPendingReassign({
        portfolio: p,
        accountIds: relevant.map((a) => a.id),
        conflicts: conflicting.map((a) => ({
          accountName: a.name,
          fromPortfolioName:
            portfolios.find((po) => po.id === a.target_portfolio_id)?.name ?? "다른 포트폴리오",
        })),
      });
      return;
    }
    onBatchSetTarget(
      p.id,
      relevant.map((a) => a.id),
    );
  }

  // 시트 안에서 고르거나 편집·자동화로 넘어가면 시트는 닫는다(삭제는 확인창이 위에 뜨므로 유지)
  const inSheet = <A extends unknown[]>(fn: (...args: A) => void) =>
    sheetOpen
      ? (...args: A) => {
          setSheetOpen(false);
          fn(...args);
        }
      : fn;

  function renderCard(p: Portfolio, dragHandleListeners?: React.HTMLAttributes<HTMLElement>) {
    return (
      <PortfolioCard
        portfolio={p}
        selected={selectedIds.has(p.id)}
        targetState={getPortfolioTargetState(p, stockAccounts)}
        accountLabel={getAccountLabel(p)}
        showAccountLabel={stockAccounts.length > 1}
        drift={driftByPortfolioId?.[p.id]}
        alertMode={alertByPortfolioId[p.id]?.mode}
        hasAlert={alertPortfolioIds.has(p.id)}
        isTargetPending={isTargetPending}
        dragHandleListeners={dragHandleListeners}
        onToggleSelect={inSheet(onToggleSelect)}
        onOpenEditor={inSheet(onOpenEditor)}
        onOpenAlertModal={inSheet(onOpenAlertModal)}
        onConfirmDelete={onConfirmDelete}
        onToggleTarget={handleToggleTarget}
      />
    );
  }

  function renderList() {
    return (
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <SortableContext items={portfolios.map((p) => p.id)} strategy={verticalListSortingStrategy}>
          {portfolios.map((p) => (
            <SortablePortfolioItem key={p.id} id={p.id}>
              {({ dragHandleListeners }) => renderCard(p, dragHandleListeners)}
            </SortablePortfolioItem>
          ))}
        </SortableContext>
      </DndContext>
    );
  }

  // 모바일은 목록 전체 대신 선택 1장 + 시트(plans/102 D1, 67 보류분) — 카드가 쌓여 분석 결과가 한참 아래로 밀렸다.
  // null(matchMedia 없음·SSR)은 데스크톱처럼 목록을 그린다.
  const compactSelected =
    isSmUp === false && portfolios.length > 1
      ? portfolios.find((p) => selectedIds.has(p.id))
      : undefined;

  return (
    <div className="w-full space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">포트폴리오</h3>
          {/* 자동화 합계 — 카드마다 칩이 있어 박스 배너 대신 헤더 부제 한 줄(plans/64 S3) */}
          {!isLoading && portfolios.length > 0 && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {alertPortfolioIds.size > 0
                ? [
                    autoAlertCount > 0 && `자동 실행 ${autoAlertCount}개`,
                    alertPortfolioIds.size - autoAlertCount > 0 &&
                      `알림 ${alertPortfolioIds.size - autoAlertCount}개`,
                  ]
                    .filter(Boolean)
                    .join(" · ") + ` / ${portfolios.length}개`
                : "자동화 설정 없음 — 카드의 '자동화 설정'에서 켤 수 있어요"}
            </p>
          )}
        </div>
        <button
          onClick={() => onOpenEditor(null)}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} gap-1 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 px-2 py-1 rounded-lg hover:bg-blue-50 dark:hover:bg-gray-700 transition-colors`}
        >
          <Plus size={13} /> 새로 만들기
        </button>
      </div>

      {unassignedAccounts.length > 0 && portfolios.length > 0 && (
        <div className="rounded-xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <CircleAlert size={13} className="text-amber-500 shrink-0" />
            <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
              기준 포트폴리오 미지정 계좌
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
            포트폴리오 카드에서 기준 포트폴리오 지정 버튼을 클릭해 지정하세요.
          </p>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 size={20} className="animate-spin text-gray-400 dark:text-gray-500" />
        </div>
      ) : portfolios.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 dark:border-gray-700 p-5 text-center space-y-4">
          <Target size={28} className="mx-auto text-gray-400 dark:text-gray-500" />
          <div>
            <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">
              첫 포트폴리오를 만들어 보세요
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              종목과 목표 비중을 설정하면 현재 보유 현황과 비교해 리밸런싱 가이드를 제공합니다.
            </p>
          </div>
          <div className="flex flex-col gap-1.5 text-left">
            {(["① 종목·비중 입력", "② 리밸런싱 분석 확인", "③ 자동화 설정"] as const).map(
              (step) => (
                <div
                  key={step}
                  className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-blue-300 dark:bg-blue-700 shrink-0" />
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
      ) : compactSelected ? (
        <>
          {renderCard(compactSelected)}
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className={`${TOUCH_HEIGHT_MIN} w-full flex items-center justify-center gap-1 text-sm font-medium text-blue-600 dark:text-blue-400 rounded-xl border border-dashed border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
          >
            <ArrowLeftRight size={14} /> 다른 포트폴리오 보기 ({portfolios.length}개)
          </button>
        </>
      ) : (
        renderList()
      )}
      {sheetOpen && (
        <Modal title="포트폴리오 선택" onClose={() => setSheetOpen(false)} closeOnBackdrop>
          <ModalBody className="space-y-3">{renderList()}</ModalBody>
        </Modal>
      )}
      {pendingReassign && (
        <ConfirmModal
          message={`'${pendingReassign.portfolio.name}'을(를) 기준 포트폴리오로 다시 지정할까요?`}
          confirmLabel="변경"
          danger={false}
          onConfirm={() => {
            onBatchSetTarget(pendingReassign.portfolio.id, pendingReassign.accountIds);
            setPendingReassign(null);
          }}
          onCancel={() => setPendingReassign(null)}
        >
          <ul className="mt-2 space-y-1 text-xs text-gray-500 dark:text-gray-400">
            {pendingReassign.conflicts.map((c) => (
              <li key={c.accountName} className="flex flex-wrap items-center gap-1">
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {c.accountName}
                </span>
                <span>{c.fromPortfolioName}</span>
                <span aria-hidden="true">→</span>
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {pendingReassign.portfolio.name}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
            기존 지정은 자동으로 해제돼요.
          </p>
        </ConfirmModal>
      )}
    </div>
  );
}
