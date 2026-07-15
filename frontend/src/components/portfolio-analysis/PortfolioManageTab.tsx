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
import {
  fetchAccounts,
  batchSetTargetPortfolio,
  type AccountTaxType,
  type InvestmentHorizon,
} from "@/api/assets";
import { fetchRebalancingAlerts } from "@/api/alerts";
import UnifiedPortfolioEditor from "./UnifiedPortfolioEditor";
import PortfolioListSection from "./PortfolioListSection";
import ErrorBoundary from "@/components/ErrorBoundary";
import ConfirmModal from "@/components/common/ConfirmModal";
import RebalancingAlertModalRouter from "@/components/rebalancing/RebalancingAlertModalRouter";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { invalidatePortfolioData, invalidateAccountData } from "@/utils/queryInvalidation";
import { mergeAlertsByPortfolio } from "@/utils/portfolio";
import { isStockAccount } from "@/utils/accounts";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";

interface Props {
  selectedPortfolioId?: string;
  onAnalyze: (portfolioId: string) => void;
  /** 추천 비중 카드 등에서 "이 비중으로 새 포트폴리오 만들기"를 눌렀을 때 채울 초기 종목/이름/분석 대상 계좌. */
  prefillItems?: PortfolioItem[] | null;
  prefillName?: string;
  prefillAccountIds?: string[] | null;
  /** prefillItems를 소비(편집 모달 오픈)한 뒤 부모 state를 비우도록 알린다 — 재오픈 방지. */
  onPrefillConsumed?: () => void;
}

export default function PortfolioManageTab({
  selectedPortfolioId,
  onAnalyze,
  prefillItems,
  prefillName,
  prefillAccountIds,
  onPrefillConsumed,
}: Props) {
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
  const stockAccounts = activeAccounts.filter((a) => isStockAccount(a.asset_type));

  const { data: rebalancingAlertsRaw } = useQuery({
    queryKey: QUERY_KEYS.rebalancingAlerts,
    queryFn: fetchRebalancingAlerts,
    staleTime: STALE_TIME.MEDIUM,
  });
  const rebalancingAlerts = useMemo(
    () => (Array.isArray(rebalancingAlertsRaw) ? rebalancingAlertsRaw : []),
    [rebalancingAlertsRaw],
  );
  const alertByPortfolioId = useMemo(
    () => mergeAlertsByPortfolio(rebalancingAlerts),
    [rebalancingAlerts],
  );
  const alertPortfolioIds = useMemo(
    () => new Set(Object.keys(alertByPortfolioId)),
    [alertByPortfolioId],
  );
  const autoAlertCount = useMemo(
    () => Object.values(alertByPortfolioId).filter((a) => a.mode === "AUTO").length,
    [alertByPortfolioId],
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

  // prefillItems가 있으면(추천 비중 카드에서 "새 포트폴리오 만들기" 클릭) 항상 신규 생성 모드로
  // 편집 모달을 연다 — editingPortfolio를 별도로 초기화할 필요 없이 렌더 시점에 파생시킨다.
  const isEditorOpen = editorOpen || !!prefillItems;
  const editingTarget = prefillItems ? null : editingPortfolio;

  function closeEditor() {
    setEditorOpen(false);
    setEditingPortfolio(null);
    onPrefillConsumed?.();
  }

  // 진단 탭의 "자동화 설정" CTA에서 넘어온 경우 자동화 설정 모달을 마운트 시점에 자동으로 연다.
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
      investment_horizon: InvestmentHorizon | null;
      tax_type: AccountTaxType | null;
    }) => createPortfolio(args),
    onSuccess: () => {
      void invalidatePortfolioData(qc);
      closeEditor();
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
      investment_horizon: InvestmentHorizon | null;
      tax_type: AccountTaxType | null;
    }) =>
      updatePortfolio(args.id, {
        name: args.name,
        items: args.items,
        base_type: args.base_type,
        account_ids: args.account_ids,
        investment_horizon: args.investment_horizon,
        tax_type: args.tax_type,
      }),
    onSuccess: () => {
      void invalidatePortfolioData(qc);
      closeEditor();
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
        toast("기준 포트폴리오 지정이 해제되었습니다", "success");
      } else {
        const pName = sortedPortfolios.find((p) => p.id === pid)?.name ?? "";
        toast(`${pName}가 ${accountIds.length}개 계좌의 기준으로 지정되었습니다`, "success");
      }
    },
    onError: (e) => toast(extractErrorMessage(e, "기준 포트폴리오 설정에 실패했습니다"), "error"),
  });

  function handleSave(
    name: string,
    items: PortfolioItem[],
    baseType: string,
    accountIds: string[] | null,
    investmentHorizon: InvestmentHorizon | null,
    taxType: AccountTaxType | null,
  ) {
    if (editingTarget) {
      updateMut.mutate({
        id: editingTarget.id,
        name,
        items,
        base_type: baseType,
        account_ids: accountIds,
        investment_horizon: investmentHorizon,
        tax_type: taxType,
      });
    } else {
      createMut.mutate({
        name,
        items,
        base_type: baseType,
        account_ids: accountIds,
        investment_horizon: investmentHorizon,
        tax_type: taxType,
      });
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

      {isEditorOpen && (
        <UnifiedPortfolioEditor
          initial={editingTarget}
          initialItems={prefillItems ?? undefined}
          initialName={prefillName}
          initialAccountIds={prefillAccountIds ?? undefined}
          accounts={stockAccounts}
          onSave={handleSave}
          onClose={closeEditor}
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
      {alertModalPortfolioId &&
        (() => {
          const alertPortfolio = sortedPortfolios.find((p) => p.id === alertModalPortfolioId);
          return (
            <RebalancingAlertModalRouter
              key={alertModalPortfolioId}
              portfolioId={alertModalPortfolioId}
              portfolioName={alertPortfolio?.name ?? ""}
              alertScope={alertPortfolio?.alert_scope}
              accountIds={alertPortfolio?.account_ids ?? null}
              accounts={accounts}
              onClose={() => setAlertModalPortfolioId(null)}
            />
          );
        })()}
    </ErrorBoundary>
  );
}
