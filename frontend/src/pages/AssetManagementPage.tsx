import { lazy, Suspense, useCallback, useMemo, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Plus, Building2, TrendingUp, Home } from "lucide-react";
import {
  RealEstateAccountModal,
  RealEstateEditModal,
  RealEstateAccountCard,
} from "@/components/assets/RealEstateSection";
import BankAccountCard from "@/components/assets/BankAccountCard";

const StockPositionsModal = lazy(() => import("@/components/assets/StockPositionsModal"));
const TransactionModal = lazy(() => import("@/components/assets/TransactionModal"));
const BankAccountModal = lazy(() => import("@/components/assets/BankAccountModal"));
const StockAccountModal = lazy(() => import("@/components/assets/StockAccountModal"));
import StockAccountCard, { type AccountStats } from "@/components/assets/StockAccountCard";
import StockAccountSummaryCard from "@/components/assets/StockAccountSummaryCard";
import TransactionHistoryTab from "@/components/assets/TransactionHistoryTab";
import ConfirmModal from "@/components/common/ConfirmModal";
import SkeletonCard from "@/components/common/SkeletonCard";
import EmptyState from "@/components/common/EmptyState";
import { invalidateAccountData } from "@/utils/queryInvalidation";
import { useRegisterRefresh } from "@/hooks/useRegisterRefresh";
import { BANK_TYPES, STOCK_TYPES, REAL_ESTATE_TYPES } from "@/constants";
import { useAssetManagementData } from "@/hooks/useAssetManagementData";
import { useAssetModals } from "@/hooks/useAssetModals";
import { useAccountMutations } from "@/hooks/useAccountMutations";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { ASSET_MANAGEMENT_TABS } from "@/constants/tabs";
import Tabs from "@/components/common/Tabs";

const TABS = ASSET_MANAGEMENT_TABS;
type Tab = (typeof TABS)[number];

export default function AssetManagementPage() {
  const [tab, setTab] = useState<Tab>("은행계좌");
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
  const { accounts, isLoading, overview, allTx, usdRate } = useAssetManagementData(tab);

  const {
    createMutation,
    deleteMutation,
    updateBankMutation,
    updateStockMutation,
    updateDepositMutation,
    updateNameMutation,
    updateRealEstateMutation,
    handleSyncBank,
    handleSyncKisAccount,
    deletingId,
    setDeletingId,
    syncingBankId,
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

  const stockAccountStats = useMemo(() => {
    const portfolioAccMap = Object.fromEntries((overview?.accounts ?? []).map((a) => [a.id, a]));
    const txByAcc: Record<string, { deposit: number; dividend: number }> = {};
    for (const t of allTx) {
      if (!t.account_id) continue;
      if (!txByAcc[t.account_id]) txByAcc[t.account_id] = { deposit: 0, dividend: 0 };
      if (t.transaction_type === "DEPOSIT") txByAcc[t.account_id].deposit += t.amount;
      if (t.transaction_type === "DIVIDEND") txByAcc[t.account_id].dividend += t.amount;
    }
    return stockAccounts.map((account) => {
      const pa = portfolioAccMap[account.id];
      const tx = txByAcc[account.id] ?? { deposit: 0, dividend: 0 };
      return {
        account,
        stats: {
          amount_krw: pa?.amount_krw ?? 0,
          invested_krw: pa?.invested_krw ?? 0,
          unrealized_pnl: pa?.unrealized_pnl ?? 0,
          deposit_total: tx.deposit,
          dividend_total: tx.dividend,
        } as AccountStats,
      };
    });
  }, [stockAccounts, overview, allTx]);

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          계좌를 등록하고 입출금·배당 내역을 관리합니다.
        </p>
      </div>

      <Tabs
        tabs={TABS}
        activeTab={tab}
        onChange={setTab}
        variant="pill"
        className="w-full sm:w-fit mb-6"
      />

      <div ref={tabContentRef}>
        {tab === "입출금·배당" && <TransactionHistoryTab accounts={accounts} />}

        {tab === "부동산" && (
          <>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                <Home size={18} />
                <span className="text-sm font-medium">
                  부동산 {isLoading ? "" : `(${realEstateAccounts.length}개)`}
                </span>
              </div>
              <button
                onClick={() => setShowRealEstateModal(true)}
                className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
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
                  action={{ label: "+ 부동산 추가하기", onClick: () => setShowRealEstateModal(true) }}
                />
              </div>
            ) : (
              <div className="space-y-3">
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

        {tab !== "입출금·배당" && tab !== "부동산" && (
          <>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                {tab === "은행계좌" ? <Building2 size={18} /> : <TrendingUp size={18} />}
                <span className="text-sm font-medium">
                  {tab} {isLoading ? "" : `(${currentBankOrStock.length}개)`}
                </span>
              </div>
              <button
                onClick={() =>
                  tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true)
                }
                className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
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
                  title={`등록된 ${tab}이 없습니다.`}
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
                    onSync={handleSyncBank}
                    isDeleting={deletingId === account.id && deleteMutation.isPending}
                    isSyncing={syncingBankId === account.id}
                  />
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {/* 증권계좌 전체 요약 */}
                <StockAccountSummaryCard
                  stockAccounts={stockAccounts}
                  overview={overview}
                  allTx={allTx}
                  usdRate={usdRate}
                />
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
                    onEditDeposit={(id, krw, usd) =>
                      updateDepositMutation.mutate({ id, deposit_krw: krw, deposit_usd: usd })
                    }
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
            readonly={
              positionsAccount.dataSource === "KIS_API" ||
              positionsAccount.dataSource === "KIWOOM_API"
            }
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
