import { useEffect, useMemo, useRef, useState } from "react";
import { arrayMove } from "@dnd-kit/sortable";
import { DragEndEvent } from "@dnd-kit/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Portfolio,
  PortfolioItem,
  createPortfolio,
  deletePortfolio,
  fetchPortfolios,
  reorderPortfolios,
  updatePortfolio,
} from "@/api/portfolios";
import { fetchAccounts, batchSetTargetPortfolio } from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import UnifiedPortfolioEditor from "./UnifiedPortfolioEditor";
import { AnalysisPanel } from "./AnalysisPanel";
import PortfolioDiagnosisCard from "./PortfolioDiagnosisCard";
import PortfolioListSection from "./PortfolioListSection";
import ErrorBoundary from "@/components/ErrorBoundary";
import ConfirmModal from "@/components/common/ConfirmModal";
import RebalancingAlertModal from "./RebalancingAlertModal";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData, invalidateAccountData } from "@/utils/queryInvalidation";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

export default function PortfolioAnalysisTab({ portfolioId }: { portfolioId?: string }) {
  const qc = useQueryClient();

  const { data: portfoliosRaw, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });
  const portfolios = Array.isArray(portfoliosRaw) ? portfoliosRaw : [];

  const [localOrder, setLocalOrder] = useState<string[]>([]);
  const sortedPortfolios = useMemo(() => {
    if (!localOrder.length || localOrder.length !== portfolios.length) return portfolios;
    const orderMap = new Map(localOrder.map((id, i) => [id, i]));
    return [...portfolios].sort((a, b) => (orderMap.get(a.id) ?? Infinity) - (orderMap.get(b.id) ?? Infinity));
  }, [portfolios, localOrder]);

  const { data: accountsRaw } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });
  const accounts = Array.isArray(accountsRaw) ? accountsRaw : [];
  const activeAccounts = accounts.filter((a) => a.is_active);
  const stockAccounts = activeAccounts.filter((a) =>
    ["STOCK_KIS", "STOCK_OTHER"].includes(a.asset_type),
  );

  const { data: rebalancingAlertsRaw } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const rebalancingAlerts = Array.isArray(rebalancingAlertsRaw) ? rebalancingAlertsRaw : [];
  const alertPortfolioIds = useMemo(
    () => new Set(rebalancingAlerts.map((a) => a.portfolio_id)),
    [rebalancingAlerts],
  );
  const alertByPortfolioId = useMemo(
    () => Object.fromEntries(rebalancingAlerts.map((a) => [a.portfolio_id, a])),
    [rebalancingAlerts],
  );

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [alertModalPortfolioId, setAlertModalPortfolioId] = useState<string | null>(null);

  const analysisSectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!portfolioId || portfolios.length === 0) return;
    if (!portfolios.some((p) => p.id === portfolioId)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedIds(new Set([portfolioId]));
    setTimeout(() => {
      analysisSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 150);
  }, [portfolioId, portfolios]);

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
    onSuccess: () => { invalidatePortfolioData(qc); setEditorOpen(false); },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 저장에 실패했습니다"), "error"),
  });

  const updateMut = useMutation({
    mutationFn: (args: { id: string; name: string; items: PortfolioItem[]; base_type: string; account_ids: string[] | null }) =>
      updatePortfolio(args.id, { name: args.name, items: args.items, base_type: args.base_type, account_ids: args.account_ids }),
    onSuccess: () => { invalidatePortfolioData(qc); setEditingPortfolio(null); setEditorOpen(false); },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 수정에 실패했습니다"), "error"),
  });

  const deleteMut = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: (_, id) => {
      invalidatePortfolioData(qc);
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(id); return next; });
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 삭제에 실패했습니다"), "error"),
  });

  const batchTargetMut = useMutation({
    mutationFn: ({ portfolioId: pid, accountIds }: { portfolioId: string | null; accountIds: string[] }) =>
      batchSetTargetPortfolio(pid, accountIds),
    onSuccess: (_, { portfolioId: pid, accountIds }) => {
      invalidateAccountData(qc);
      if (pid === null) {
        toast("목표 포트폴리오 지정이 해제되었습니다");
      } else {
        const pName = sortedPortfolios.find((p) => p.id === pid)?.name ?? "";
        toast(`${pName}가 ${accountIds.length}개 계좌의 목표로 지정되었습니다`);
      }
    },
    onError: (e) => toast(extractErrorMessage(e, "목표 포트폴리오 설정에 실패했습니다"), "error"),
  });

  function handleSave(name: string, items: PortfolioItem[], baseType: string, accountIds: string[] | null) {
    if (editingPortfolio) {
      updateMut.mutate({ id: editingPortfolio.id, name, items, base_type: baseType, account_ids: accountIds });
    } else {
      createMut.mutate({ name, items, base_type: baseType, account_ids: accountIds });
    }
  }

  const selectedNames = sortedPortfolios
    .filter((p) => selectedIds.has(p.id))
    .map((p) => p.name)
    .join(", ");

  return (
    <div className="space-y-5">
      <ErrorBoundary variant="section">
        <PortfolioDiagnosisCard />
      </ErrorBoundary>

      <hr className="border-gray-200 dark:border-gray-700" />

      <div className="flex flex-col md:flex-row gap-4 md:gap-6">
        <PortfolioListSection
          portfolios={sortedPortfolios}
          isLoading={isLoading}
          selectedIds={selectedIds}
          stockAccounts={stockAccounts}
          alertPortfolioIds={alertPortfolioIds}
          alertByPortfolioId={alertByPortfolioId}
          isTargetPending={batchTargetMut.isPending}
          onDragEnd={handleDragEnd}
          onToggleSelect={(id) =>
            setSelectedIds((prev) => {
              const next = new Set(prev);
              if (next.has(id)) next.delete(id); else next.add(id);
              return next;
            })
          }
          onOpenEditor={(p) => { setEditingPortfolio(p); setEditorOpen(true); }}
          onOpenAlertModal={setAlertModalPortfolioId}
          onConfirmDelete={setConfirmDeleteId}
          onBatchSetTarget={(pid, accountIds) => batchTargetMut.mutate({ portfolioId: pid, accountIds })}
          onRefresh={async () => {
            await qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolios });
          }}
        />

        <div ref={analysisSectionRef}>
          <ErrorBoundary variant="section">
            <AnalysisPanel
              selectedIds={selectedIds}
              selectedNames={selectedNames}
              portfolios={sortedPortfolios}
              activeAccounts={activeAccounts}
              onOpenAlertModal={setAlertModalPortfolioId}
              autoAnalyzeId={portfolioId}
            />
          </ErrorBoundary>
        </div>
      </div>

      {editorOpen && (
        <UnifiedPortfolioEditor
          initial={editingPortfolio}
          accounts={stockAccounts}
          onSave={handleSave}
          onClose={() => { setEditorOpen(false); setEditingPortfolio(null); }}
          saving={createMut.isPending || updateMut.isPending}
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
          accountIds={sortedPortfolios.find((p) => p.id === alertModalPortfolioId)?.account_ids ?? null}
          onClose={() => setAlertModalPortfolioId(null)}
        />
      )}
    </div>
  );
}
