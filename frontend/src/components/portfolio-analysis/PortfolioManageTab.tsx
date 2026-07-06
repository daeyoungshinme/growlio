import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
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
import { fetchDriftSummary, PortfolioDriftSummary } from "@/api/rebalancing";
import { fetchAccounts, batchSetTargetPortfolio } from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import UnifiedPortfolioEditor from "./UnifiedPortfolioEditor";
import PortfolioListSection from "./PortfolioListSection";
import ErrorBoundary from "@/components/ErrorBoundary";
import ConfirmModal from "@/components/common/ConfirmModal";
import RebalancingAlertModal from "@/components/rebalancing/RebalancingAlertModal";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData, invalidateAccountData } from "@/utils/queryInvalidation";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { usePendingRecommendationStore } from "@/stores/pendingRecommendationStore";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

interface Props {
  selectedPortfolioId?: string;
  onAnalyze: (portfolioId: string) => void;
}

export default function PortfolioManageTab({ selectedPortfolioId, onAnalyze }: Props) {
  const qc = useQueryClient();

  const { data: portfoliosRaw, isLoading } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
  });

  const handleRefresh = useCallback(async () => {
    await qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolios });
  }, [qc]);
  useRegisterRefresh(handleRefresh);
  const portfolios = useMemo(
    () => (Array.isArray(portfoliosRaw) ? portfoliosRaw : []),
    [portfoliosRaw],
  );

  const [localOrder, setLocalOrder] = useState<string[]>([]);
  const sortedPortfolios = useMemo(() => {
    if (!localOrder.length || localOrder.length !== portfolios.length) return portfolios;
    const orderMap = new Map(localOrder.map((id, i) => [id, i]));
    return [...portfolios].sort(
      (a, b) => (orderMap.get(a.id) ?? Infinity) - (orderMap.get(b.id) ?? Infinity),
    );
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
  const rebalancingAlerts = useMemo(
    () => (Array.isArray(rebalancingAlertsRaw) ? rebalancingAlertsRaw : []),
    [rebalancingAlertsRaw],
  );
  const alertPortfolioIds = useMemo(
    () => new Set(rebalancingAlerts.map((a) => a.portfolio_id)),
    [rebalancingAlerts],
  );
  const autoAlertCount = useMemo(
    () => rebalancingAlerts.filter((a) => a.mode === "AUTO").length,
    [rebalancingAlerts],
  );
  const alertByPortfolioId = useMemo(
    () => Object.fromEntries(rebalancingAlerts.map((a) => [a.portfolio_id, a])),
    [rebalancingAlerts],
  );

  const { data: driftSummaryRaw } = useQuery({
    queryKey: QUERY_KEYS.driftSummary,
    queryFn: fetchDriftSummary,
    staleTime: STALE_TIME.MEDIUM,
    enabled: portfolios.length > 0,
  });
  const driftByPortfolioId = useMemo<Record<string, PortfolioDriftSummary>>(() => {
    const list = Array.isArray(driftSummaryRaw) ? driftSummaryRaw : [];
    return Object.fromEntries(list.map((s) => [s.portfolio_id, s]));
  }, [driftSummaryRaw]);

  const [editorOpen, setEditorOpen] = useState(false);
  const [editingPortfolio, setEditingPortfolio] = useState<Portfolio | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  // 진단 탭의 "알림 설정" CTA에서 넘어온 경우 알림 설정 모달을 마운트 시점에 자동으로 연다.
  const [searchParams, setSearchParams] = useSearchParams();
  const [alertModalPortfolioId, setAlertModalPortfolioId] = useState<string | null>(() =>
    searchParams.get("openAlert") === "1" && selectedPortfolioId ? selectedPortfolioId : null,
  );

  useEffect(() => {
    if (searchParams.get("openAlert") !== "1") return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete("openAlert");
        return next;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams]);

  // GoalRecommendationCard의 "적용" 클릭을 받아 해당 포트폴리오 편집기를 추천 비중으로 미리 채워 연다.
  const pendingRecommendation = usePendingRecommendationStore((s) => s.pending);
  const clearPendingRecommendation = usePendingRecommendationStore((s) => s.clearPending);
  useEffect(() => {
    if (!pendingRecommendation) return;
    const portfolio = portfolios.find((p) => p.id === pendingRecommendation.portfolioId);
    if (!portfolio) return;
    // 다른 컴포넌트(GoalRecommendationCard)가 발행한 외부 스토어 신호를 편집기 상태로 반영 — 1회성 소비 후 즉시 clear.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setEditingPortfolio({ ...portfolio, items: pendingRecommendation.items });
    setEditorOpen(true);
    clearPendingRecommendation();
  }, [pendingRecommendation, portfolios, clearPendingRecommendation]);

  const selectedIds = useMemo(
    () => (selectedPortfolioId ? new Set([selectedPortfolioId]) : new Set<string>()),
    [selectedPortfolioId],
  );

  // 포트폴리오가 1개면 자동 선택 (분석 탭으로 넘어가지 않고 강조만)
  const initialSelectionDone = useRef(false);
  useEffect(() => {
    if (initialSelectionDone.current || portfolios.length !== 1) return;
    initialSelectionDone.current = true;
  }, [portfolios]);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const currentIds = sortedPortfolios.map((p) => p.id);
    const oldIndex = currentIds.indexOf(active.id as string);
    const newIndex = currentIds.indexOf(over.id as string);
    const newOrder = arrayMove(currentIds, oldIndex, newIndex);
    setLocalOrder(newOrder);
    void reorderPortfolios(newOrder.map((id, i) => ({ id, sort_order: i }))).catch(() => {
      setLocalOrder(currentIds);
      toast("순서 변경에 실패했습니다");
    });
  }

  const createMut = useMutation({
    mutationFn: (args: {
      name: string;
      items: PortfolioItem[];
      base_type: string;
      account_ids: string[] | null;
    }) => createPortfolio(args),
    onSuccess: () => {
      void invalidatePortfolioData(qc);
      setEditorOpen(false);
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 저장에 실패했습니다"), "error"),
  });

  const updateMut = useMutation({
    mutationFn: (args: {
      id: string;
      name: string;
      items: PortfolioItem[];
      base_type: string;
      account_ids: string[] | null;
    }) =>
      updatePortfolio(args.id, {
        name: args.name,
        items: args.items,
        base_type: args.base_type,
        account_ids: args.account_ids,
      }),
    onSuccess: () => {
      void invalidatePortfolioData(qc);
      setEditingPortfolio(null);
      setEditorOpen(false);
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 수정에 실패했습니다"), "error"),
  });

  const deleteMut = useMutation({
    mutationFn: deletePortfolio,
    onSuccess: () => {
      void invalidatePortfolioData(qc);
    },
    onError: (e) => toast(extractErrorMessage(e, "포트폴리오 삭제에 실패했습니다"), "error"),
  });

  const batchTargetMut = useMutation({
    mutationFn: ({
      portfolioId,
      accountIds,
    }: {
      portfolioId: string | null;
      accountIds: string[];
    }) => batchSetTargetPortfolio(portfolioId, accountIds),
    onSuccess: (_, { portfolioId: pid, accountIds }) => {
      void invalidateAccountData(qc);
      if (pid === null) {
        toast("목표 포트폴리오 지정이 해제되었습니다");
      } else {
        const pName = sortedPortfolios.find((p) => p.id === pid)?.name ?? "";
        toast(`${pName}가 ${accountIds.length}개 계좌의 목표로 지정되었습니다`);
      }
    },
    onError: (e) => toast(extractErrorMessage(e, "목표 포트폴리오 설정에 실패했습니다"), "error"),
  });

  function handleSave(
    name: string,
    items: PortfolioItem[],
    baseType: string,
    accountIds: string[] | null,
  ) {
    if (editingPortfolio) {
      updateMut.mutate({
        id: editingPortfolio.id,
        name,
        items,
        base_type: baseType,
        account_ids: accountIds,
      });
    } else {
      createMut.mutate({ name, items, base_type: baseType, account_ids: accountIds });
    }
  }

  return (
    <ErrorBoundary variant="section">
      <PortfolioListSection
        portfolios={sortedPortfolios}
        isLoading={isLoading}
        selectedIds={selectedIds}
        stockAccounts={stockAccounts}
        alertPortfolioIds={alertPortfolioIds}
        autoAlertCount={autoAlertCount}
        alertByPortfolioId={alertByPortfolioId}
        driftByPortfolioId={driftByPortfolioId}
        isTargetPending={batchTargetMut.isPending}
        onDragEnd={handleDragEnd}
        onToggleSelect={(id) => onAnalyze(id)}
        onOpenEditor={(p) => {
          setEditingPortfolio(p);
          setEditorOpen(true);
        }}
        onOpenAlertModal={setAlertModalPortfolioId}
        onConfirmDelete={setConfirmDeleteId}
        onBatchSetTarget={(pid, accountIds) =>
          batchTargetMut.mutate({ portfolioId: pid, accountIds })
        }
      />

      {editorOpen && (
        <UnifiedPortfolioEditor
          initial={editingPortfolio}
          accounts={stockAccounts}
          onSave={handleSave}
          onClose={() => {
            setEditorOpen(false);
            setEditingPortfolio(null);
          }}
          saving={createMut.isPending || updateMut.isPending}
        />
      )}
      {confirmDeleteId && (
        <ConfirmModal
          message="포트폴리오를 삭제하시겠습니까?"
          confirmLabel="삭제"
          onConfirm={() => {
            deleteMut.mutate(confirmDeleteId);
            setConfirmDeleteId(null);
          }}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}
      {alertModalPortfolioId && (
        <RebalancingAlertModal
          key={alertModalPortfolioId}
          portfolioId={alertModalPortfolioId}
          portfolioName={sortedPortfolios.find((p) => p.id === alertModalPortfolioId)?.name ?? ""}
          accountIds={
            sortedPortfolios.find((p) => p.id === alertModalPortfolioId)?.account_ids ?? null
          }
          onClose={() => setAlertModalPortfolioId(null)}
        />
      )}
    </ErrorBoundary>
  );
}
