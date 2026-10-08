import { lazy, Suspense, useCallback, useEffect, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Building2, TrendingUp, Home } from "lucide-react";
import {
  RealEstateAccountModal,
  RealEstateEditModal,
  RealEstateAccountCard,
  RealEstateSummaryCard,
} from "@/components/assets/RealEstateSection";
import BankAccountCard from "@/components/assets/BankAccountCard";

const StockPositionsModal = lazy(() => import("@/components/assets/StockPositionsModal"));
const TransactionModal = lazy(() => import("@/components/assets/TransactionModal"));
const BankAccountModal = lazy(() => import("@/components/assets/BankAccountModal"));
const StockAccountModal = lazy(() => import("@/components/assets/StockAccountModal"));
import StockAccountCard from "@/components/assets/StockAccountCard";
import StockAccountSummaryCard from "@/components/assets/StockAccountSummaryCard";
import AccountHistoryTab from "@/components/assets/AccountHistoryTab";
import { legacyHistorySegment } from "@/utils/legacyTabRedirect";
import ConfirmModal from "@/components/common/ConfirmModal";
import SkeletonCard from "@/components/common/SkeletonCard";
import EmptyState from "@/components/common/EmptyState";
import { invalidateAccountData } from "@/utils/queryInvalidation";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { BANK_TYPES, STOCK_TYPES, REAL_ESTATE_TYPES } from "@/constants";
import { useAssetManagementData } from "@/hooks/useAssetManagementData";
import { useAssetModals } from "@/hooks/useAssetModals";
import { useAccountMutations } from "@/hooks/useAccountMutations";
import { isSyncableAccount } from "@/utils/accounts";
import { useStockAccountStats } from "@/hooks/useStockAccountStats";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { ASSET_MANAGEMENT_TABS } from "@/constants/tabs";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import Tabs from "@/components/common/Tabs";

const TABS = ASSET_MANAGEMENT_TABS;
type Tab = (typeof TABS)[number];

export default function AssetManagementPage() {
  // 온보딩 딥링크(`/assets?tab=계좌관리&atab=증권계좌`)등이 특정 서브탭으로 바로 진입할 수
  // 있도록 URL 쿼리로 동기화한다(PortfolioPage의 `portfolioTab` 패턴과 동일).
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("atab");
  // 입출금·배당/기간별 매수는 "내역" 탭 세그먼트로 통합(plans/50 M2) — 옛 링크는 URL을 새 형태로 고쳐 쓴다
  const legacySegment = legacyHistorySegment(rawTab);
  useEffect(() => {
    if (!legacySegment) return;
    setSearchParams(
      (prev) => {
        prev.set("atab", "내역");
        prev.set("history", legacySegment);
        return prev;
      },
      { replace: true },
    );
  }, [legacySegment, setSearchParams]);
  const tab: Tab = legacySegment
    ? "내역"
    : TABS.includes(rawTab as Tab)
      ? (rawTab as Tab)
      : "은행계좌";
  const setTab = useCallback(
    (next: Tab) => {
      setSearchParams(
        (prev) => {
          prev.set("atab", next);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );
  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, TABS, tab, setTab);

  const {
    showBankModal,
    setShowBankModal,
    showStockModal,
    setShowStockModal,
    showRealEstateModal,
    setShowRealEstateModal,
    editingRealEstate,
    setEditingRealEstate,
    editingBankAccount,
    setEditingBankAccount,
    editingStockAccount,
    setEditingStockAccount,
    confirmDeleteId,
    setConfirmDeleteId,
    positionsAccount,
    setPositionsAccount,
    txAccount,
    setTxAccount,
  } = useAssetModals();

  const queryClient = useQueryClient();

  const handleRefresh = useCallback(async () => {
    await invalidateAccountData(queryClient);
  }, [queryClient]);
  useRegisterRefresh(handleRefresh);
  const { accounts, isLoading, error, overview, allTx, usdRate } = useAssetManagementData(tab);

  const {
    createMutation,
    deleteMutation,
    updateBankMutation,
    updateStockMutation,
    updateDepositMutation,
    updateNameMutation,
    updateRealEstateMutation,
    handleSyncKisAccount,
    deletingId,
    setDeletingId,
    syncingStockIds,
  } = useAccountMutations({
    onBankModalClose: () => setShowBankModal(false),
    onStockModalClose: () => setShowStockModal(false),
    onEditBankClose: () => setEditingBankAccount(null),
    onEditRealEstateClose: () => setEditingRealEstate(null),
    onEditStockClose: () => setEditingStockAccount(null),
  });

  const handleDelete = useCallback(
    (id: string) => {
      setConfirmDeleteId(id);
    },
    [setConfirmDeleteId],
  );

  const handleConfirmDelete = useCallback(() => {
    if (!confirmDeleteId) return;
    setDeletingId(confirmDeleteId);
    deleteMutation.mutate(confirmDeleteId);
    setConfirmDeleteId(null);
  }, [confirmDeleteId, deleteMutation, setDeletingId, setConfirmDeleteId]);

  const bankAccounts = accounts.filter((a) => BANK_TYPES.includes(a.asset_type));
  const stockAccounts = accounts.filter((a) => STOCK_TYPES.includes(a.asset_type));
  const realEstateAccounts = accounts.filter((a) => REAL_ESTATE_TYPES.includes(a.asset_type));
  const currentBankOrStock = tab === "은행계좌" ? bankAccounts : stockAccounts;

  const stockAccountStats = useStockAccountStats(stockAccounts, overview, allTx);

  if (error)
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-sm text-red-500">계좌 정보를 불러오지 못했습니다</p>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: QUERY_KEYS.accounts })}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors`}
        >
          다시 시도
        </button>
      </div>
    );

  return (
    <div className="max-w-2xl mx-auto">
      <Tabs tabs={TABS} activeTab={tab} onChange={setTab} variant="underline" className="mb-6" />

      <div ref={tabContentRef}>
        {/* 옛 링크는 URL을 고쳐 쓴 다음 렌더 — 그 전에 그리면 기본 세그먼트가 한 번 깜빡인다 */}
        {tab === "내역" && !legacySegment && <AccountHistoryTab accounts={accounts} />}

        {tab === "부동산" && (
          <>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                <Home size={18} />
                <h2 className="text-sm font-medium">
                  부동산 {isLoading ? "" : `(${realEstateAccounts.length}개)`}
                </h2>
              </div>
              <button
                onClick={() => setShowRealEstateModal(true)}
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors`}
              >
                <Plus size={16} />
                부동산 추가
              </button>
            </div>
            {isLoading ? (
              <SkeletonCard rows={3} />
            ) : realEstateAccounts.length === 0 ? (
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700">
                <EmptyState
                  title="등록된 부동산이 없습니다."
                  action={{
                    label: "+ 부동산 추가하기",
                    onClick: () => setShowRealEstateModal(true),
                  }}
                />
              </div>
            ) : (
              <div className="space-y-3">
                <RealEstateSummaryCard accounts={realEstateAccounts} />
                {realEstateAccounts.map((account) => (
                  <RealEstateAccountCard
                    key={account.id}
                    account={account}
                    onDelete={handleDelete}
                    onEdit={(acc) => setEditingRealEstate(acc)}
                    isDeleting={deletingId === account.id && deleteMutation.isPending}
                  />
                ))}
              </div>
            )}
          </>
        )}

        {(tab === "은행계좌" || tab === "증권계좌") && (
          <>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                {tab === "은행계좌" ? <Building2 size={18} /> : <TrendingUp size={18} />}
                <h2 className="text-sm font-medium">
                  {tab} {isLoading ? "" : `(${currentBankOrStock.length}개)`}
                </h2>
              </div>
              <button
                onClick={() =>
                  tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true)
                }
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors`}
              >
                <Plus size={16} />
                계좌 추가
              </button>
            </div>

            {isLoading ? (
              <SkeletonCard rows={3} />
            ) : currentBankOrStock.length === 0 ? (
              <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700">
                <EmptyState
                  title={`등록된 ${tab}가 없습니다.`}
                  action={{
                    label: "+ 계좌 추가하기",
                    onClick: () =>
                      tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true),
                  }}
                />
              </div>
            ) : tab === "은행계좌" ? (
              <div className="space-y-3">
                {bankAccounts.map((account) => (
                  <BankAccountCard
                    key={account.id}
                    account={account}
                    onDelete={handleDelete}
                    onEditModal={(id) => {
                      const acc = bankAccounts.find((a) => a.id === id);
                      if (acc) setEditingBankAccount(acc);
                    }}
                    onEditName={(id, name) => updateNameMutation.mutate({ id, name })}
                    isDeleting={deletingId === account.id && deleteMutation.isPending}
                  />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {/* 증권계좌 합계(누적 입금·배당·예수금) — 평가액은 투자현황이 권위 표면 */}
                <StockAccountSummaryCard perAccountStats={stockAccountStats} usdRate={usdRate} />
                {/* 계좌별 카드 */}
                {stockAccountStats.map(({ account, stats }) => (
                  <StockAccountCard
                    key={account.id}
                    account={account}
                    stats={stats}
                    onDelete={handleDelete}
                    onManagePositions={setPositionsAccount}
                    onTransactions={(a) =>
                      setTxAccount({ ...a, depositKrw: account.deposit_krw ?? 0 })
                    }
                    onEdit={setEditingStockAccount}
                    onEditName={(id, name) => updateNameMutation.mutate({ id, name })}
                    onSync={(id) => handleSyncKisAccount(id, accounts)}
                    isSyncing={syncingStockIds.has(account.id)}
                    isDeleting={deletingId === account.id && deleteMutation.isPending}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <Suspense fallback={null}>
        {showBankModal && (
          <BankAccountModal
            onClose={() => setShowBankModal(false)}
            onSubmit={(data) => createMutation.mutate(data)}
            isLoading={createMutation.isPending}
          />
        )}
        {editingBankAccount && (
          <BankAccountModal
            initialAccount={editingBankAccount}
            onClose={() => setEditingBankAccount(null)}
            onSubmit={(data) => updateBankMutation.mutate({ id: editingBankAccount.id, data })}
            isLoading={updateBankMutation.isPending}
          />
        )}
        {showStockModal && (
          <StockAccountModal
            onClose={() => setShowStockModal(false)}
            onSubmit={(data) => createMutation.mutate(data)}
            isLoading={createMutation.isPending}
          />
        )}
        {editingStockAccount && (
          <StockAccountModal
            initialAccount={editingStockAccount}
            onClose={() => setEditingStockAccount(null)}
            onSubmit={(data) => updateStockMutation.mutate({ id: editingStockAccount.id, data })}
            isLoading={updateStockMutation.isPending}
          />
        )}
        {positionsAccount && (
          <StockPositionsModal
            accountId={positionsAccount.id}
            accountName={positionsAccount.name}
            readonly={isSyncableAccount(positionsAccount.dataSource)}
            onClose={() => {
              setPositionsAccount(null);
              void invalidateAccountData(queryClient);
            }}
          />
        )}
        {txAccount && (
          <TransactionModal
            accountId={txAccount.id}
            accountName={txAccount.name}
            depositKrw={txAccount.depositKrw}
            onDepositUpdate={(newDeposit) =>
              updateDepositMutation.mutate({ id: txAccount.id, deposit_krw: newDeposit })
            }
            onClose={() => {
              setTxAccount(null);
              void invalidateAccountData(queryClient);
            }}
          />
        )}
      </Suspense>
      {showRealEstateModal && (
        <RealEstateAccountModal
          onClose={() => setShowRealEstateModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending}
        />
      )}
      {editingRealEstate && (
        <RealEstateEditModal
          account={editingRealEstate}
          onClose={() => setEditingRealEstate(null)}
          onSubmit={(id, data) => updateRealEstateMutation.mutate({ id, data })}
          isLoading={updateRealEstateMutation.isPending}
        />
      )}
      {confirmDeleteId && (
        <ConfirmModal
          message="계좌를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다."
          confirmLabel="삭제"
          onConfirm={handleConfirmDelete}
          onCancel={() => setConfirmDeleteId(null)}
        />
      )}
    </div>
  );
}
