import { useCallback, useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Building2, TrendingUp, Home } from "lucide-react";
import {
  createAccount,
  updateAccount,
  deleteAccount,
  syncAccount,
  type AssetAccount,
} from "../api/assets";
import { extractErrorMessage } from "../utils/error";
import StockPositionsModal from "../components/assets/StockPositionsModal";
import TransactionModal from "../components/assets/TransactionModal";
import BankAccountModal from "../components/assets/BankAccountModal";
import StockAccountModal from "../components/assets/StockAccountModal";
import {
  RealEstateAccountModal,
  RealEstateEditModal,
  RealEstateAccountCard,
} from "../components/assets/RealEstateSection";
import BankAccountCard from "../components/assets/BankAccountCard";
import StockAccountCard, { type AccountStats } from "../components/assets/StockAccountCard";
import StockAccountSummaryCard from "../components/assets/StockAccountSummaryCard";
import TransactionHistoryTab from "../components/assets/TransactionHistoryTab";
import ConfirmModal from "../components/common/ConfirmModal";
import { invalidateAccountData, invalidateSyncData } from "../utils/queryInvalidation";
import { toast } from "../utils/toast";
import { BANK_TYPES, STOCK_TYPES, REAL_ESTATE_TYPES } from "../constants";
import { useAssetManagementData } from "../hooks/useAssetManagementData";
import { ASSET_MANAGEMENT_TABS } from "../constants/tabs";

const TABS = ASSET_MANAGEMENT_TABS;
type Tab = typeof TABS[number];


export default function AssetManagementPage() {
  const [tab, setTab] = useState<Tab>("은행계좌");
  const [showBankModal, setShowBankModal] = useState(false);
  const [showStockModal, setShowStockModal] = useState(false);
  const [showRealEstateModal, setShowRealEstateModal] = useState(false);
  const [editingRealEstate, setEditingRealEstate] = useState<AssetAccount | null>(null);
  const [editingBankAccount, setEditingBankAccount] = useState<AssetAccount | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [syncingBankId, setSyncingBankId] = useState<string | null>(null);
  const [syncingStockIds, setSyncingStockIds] = useState<Set<string>>(new Set());
  const [positionsAccount, setPositionsAccount] = useState<{ id: string; name: string; dataSource: string } | null>(null);
  const [txAccount, setTxAccount] = useState<{ id: string; name: string; depositKrw: number } | null>(null);

  const queryClient = useQueryClient();
  const { accounts, isLoading, overview, allTx, usdRate } = useAssetManagementData(tab);

  const invalidateAll = useCallback(() => invalidateAccountData(queryClient), [queryClient]);

  const createMutation = useMutation({
    mutationFn: createAccount,
    onSuccess: async (data) => {
      invalidateAll();
      setShowBankModal(false);
      setShowStockModal(false);
      if (data.data_source === "KIS_API" || data.data_source === "KIWOOM_API") {
        setSyncingStockIds((prev) => new Set(prev).add(data.id));
        try {
          await syncAccount(data.id);
          invalidateAll();
        } catch {
          toast("초기 동기화 실패. 계좌 카드의 동기화 버튼으로 재시도하세요.");
        } finally {
          setSyncingStockIds((prev) => {
            const next = new Set(prev);
            next.delete(data.id);
            return next;
          });
        }
      }
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌 추가에 실패했습니다"), "error"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAccount,
    onSuccess: () => {
      invalidateAll();
      setDeletingId(null);
    },
    onError: (e) => toast(extractErrorMessage(e, "계좌 삭제에 실패했습니다"), "error"),
  });

  const handleDelete = useCallback((id: string) => {
    setConfirmDeleteId(id);
  }, []);

  const handleConfirmDelete = useCallback(() => {
    if (!confirmDeleteId) return;
    setDeletingId(confirmDeleteId);
    deleteMutation.mutate(confirmDeleteId);
    setConfirmDeleteId(null);
  }, [confirmDeleteId, deleteMutation]);

  const updateBankMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(id, data),
    onSuccess: () => { invalidateAll(); setEditingBankAccount(null); },
    onError: (e) => toast(extractErrorMessage(e, "계좌 수정에 실패했습니다"), "error"),
  });

  const updateDepositMutation = useMutation({
    mutationFn: ({ id, deposit_krw, deposit_usd }: { id: string; deposit_krw: number; deposit_usd?: number }) =>
      updateAccount(id, { deposit_krw, ...(deposit_usd !== undefined ? { deposit_usd } : {}) }),
    onSuccess: () => invalidateAll(),
    onError: (e) => toast(extractErrorMessage(e, "예수금 수정에 실패했습니다"), "error"),
  });

  const updateNameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      updateAccount(id, { name }),
    onSuccess: () => invalidateAll(),
    onError: (e) => toast(extractErrorMessage(e, "계좌명 수정에 실패했습니다"), "error"),
  });

  const updateRealEstateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAccount>[1] }) =>
      updateAccount(id, data),
    onSuccess: () => {
      invalidateAll();
      setEditingRealEstate(null);
    },
    onError: (e) => toast(extractErrorMessage(e, "부동산 정보 수정에 실패했습니다"), "error"),
  });

  const handleSyncBank = useCallback(async (id: string) => {
    setSyncingBankId(id);
    try {
      await syncAccount(id);
      invalidateAll();
    } finally {
      setSyncingBankId(null);
    }
  }, [invalidateAll]);

  const handleSyncKisAccount = useCallback(async (id: string) => {
    const acc = accounts.find((a) => a.id === id);
    setSyncingStockIds((prev) => new Set(prev).add(id));
    try {
      await syncAccount(id);
      await invalidateSyncData(queryClient);
      toast("동기화 완료");
    } catch {
      const broker = acc?.asset_type === "STOCK_KIWOOM" ? "키움" : "KIS";
      toast(`동기화 실패. ${broker} API 자격증명을 확인하세요.`);
    } finally {
      setSyncingStockIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, [accounts, queryClient]);

  const bankAccounts = accounts.filter((a) => BANK_TYPES.includes(a.asset_type));
  const stockAccounts = accounts.filter((a) => STOCK_TYPES.includes(a.asset_type));
  const realEstateAccounts = accounts.filter((a) => REAL_ESTATE_TYPES.includes(a.asset_type));
  const currentBankOrStock = tab === "은행계좌" ? bankAccounts : stockAccounts;

  const stockAccountStats = useMemo(() => {
    const portfolioAccMap = Object.fromEntries(
      (overview?.accounts ?? []).map((a) => [a.id, a])
    );
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
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">계좌를 등록하고 입출금·배당 내역을 관리합니다.</p>
      </div>

      <div className="flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 w-full sm:w-fit mb-6 overflow-x-auto scrollbar-none">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`shrink-0 whitespace-nowrap px-3 py-2 sm:px-5 rounded-lg text-sm font-medium transition-colors ${
              tab === t ? "bg-white dark:bg-gray-700 shadow text-gray-900 dark:text-gray-50" : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            }`}>
            {t}
          </button>
        ))}
      </div>

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
            <button onClick={() => setShowRealEstateModal(true)}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
              <Plus size={16} />
              부동산 추가
            </button>
          </div>
          {isLoading ? (
            <div className="text-center py-12 text-gray-400 text-sm">불러오는 중...</div>
          ) : realEstateAccounts.length === 0 ? (
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-12 text-center">
              <p className="text-gray-400 dark:text-gray-500 text-sm">등록된 부동산이 없습니다.</p>
              <button onClick={() => setShowRealEstateModal(true)}
                className="mt-3 text-blue-600 dark:text-blue-400 text-sm hover:underline">
                + 부동산 추가하기
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {realEstateAccounts.map((account) => (
                <RealEstateAccountCard key={account.id} account={account}
                  onDelete={handleDelete}
                  onEdit={(acc) => setEditingRealEstate(acc)}
                  isDeleting={deletingId === account.id && deleteMutation.isPending} />
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
              onClick={() => tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true)}
              className="flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
              <Plus size={16} />
              계좌 추가
            </button>
          </div>

          {isLoading ? (
            <div className="text-center py-12 text-gray-400 text-sm">불러오는 중...</div>
          ) : currentBankOrStock.length === 0 ? (
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-12 text-center">
              <p className="text-gray-400 dark:text-gray-500 text-sm">등록된 {tab}이 없습니다.</p>
              <button
                onClick={() => tab === "은행계좌" ? setShowBankModal(true) : setShowStockModal(true)}
                className="mt-3 text-blue-600 dark:text-blue-400 text-sm hover:underline">
                + 계좌 추가하기
              </button>
            </div>
          ) : tab === "은행계좌" ? (
            <div className="space-y-3">
              {bankAccounts.map((account) => (
                <BankAccountCard key={account.id} account={account}
                  usdRate={usdRate}
                  onDelete={handleDelete}
                  onEditModal={(id) => {
                    const acc = bankAccounts.find((a) => a.id === id);
                    if (acc) setEditingBankAccount(acc);
                  }}
                  onEditName={(id, name) => updateNameMutation.mutate({ id, name })}
                  onSync={handleSyncBank}
                  isDeleting={deletingId === account.id && deleteMutation.isPending}
                  isSyncing={syncingBankId === account.id} />
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
                <StockAccountCard key={account.id} account={account} stats={stats}
                  onDelete={handleDelete}
                  onManagePositions={setPositionsAccount}
                  onTransactions={(a) => setTxAccount({ ...a, depositKrw: account.deposit_krw ?? 0 })}
                  onEditDeposit={(id, krw, usd) => updateDepositMutation.mutate({ id, deposit_krw: krw, deposit_usd: usd })}
                  onEditName={(id, name) => updateNameMutation.mutate({ id, name })}
                  onSync={handleSyncKisAccount}
                  isSyncing={syncingStockIds.has(account.id)}
                  isDeleting={deletingId === account.id && deleteMutation.isPending} />
              ))}
            </div>
          )}
        </>
      )}

      {showBankModal && (
        <BankAccountModal onClose={() => setShowBankModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending} />
      )}
      {editingBankAccount && (
        <BankAccountModal
          initialAccount={editingBankAccount}
          onClose={() => setEditingBankAccount(null)}
          onSubmit={(data) => updateBankMutation.mutate({ id: editingBankAccount.id, data })}
          isLoading={updateBankMutation.isPending} />
      )}
      {showStockModal && (
        <StockAccountModal onClose={() => setShowStockModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending} />
      )}
      {showRealEstateModal && (
        <RealEstateAccountModal onClose={() => setShowRealEstateModal(false)}
          onSubmit={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending} />
      )}
      {editingRealEstate && (
        <RealEstateEditModal
          account={editingRealEstate}
          onClose={() => setEditingRealEstate(null)}
          onSubmit={(id, data) => updateRealEstateMutation.mutate({ id, data })}
          isLoading={updateRealEstateMutation.isPending} />
      )}
      {positionsAccount && (
        <StockPositionsModal
          accountId={positionsAccount.id}
          accountName={positionsAccount.name}
          readonly={positionsAccount.dataSource === "KIS_API" || positionsAccount.dataSource === "KIWOOM_API"}
          onClose={() => {
            setPositionsAccount(null);
            void invalidateAccountData(queryClient);
          }}
        />
      )}
      {txAccount && (
        <TransactionModal accountId={txAccount.id} accountName={txAccount.name}
          depositKrw={txAccount.depositKrw}
          onDepositUpdate={(newDeposit) => updateDepositMutation.mutate({ id: txAccount.id, deposit_krw: newDeposit })}
          onClose={() => {
            setTxAccount(null);
            void invalidateAccountData(queryClient);
          }} />
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
