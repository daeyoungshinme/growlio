import { useState, useMemo, useRef } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ChevronUp, Pencil, Trash2 } from "lucide-react";
import EmptyState from "@/components/common/EmptyState";
import { updateAccount, type AssetAccount } from "@/api/assets";
import {
  fetchTransactions,
  deleteTransaction,
  type Transaction,
} from "@/api/transactions";
import { TransactionForm } from "./TransactionForm";
import { fmtKrw } from "@/utils/format";
import { invalidateAccountData, invalidateTransactionData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { STOCK_TYPES } from "@/constants";
import { TX_LABELS, TX_COLORS } from "@/constants/transaction";
import { INPUT_SM } from "@/constants/inputStyles";
import { extractErrorMessage } from "@/utils/error";

const currentYear = new Date().getFullYear();
const YEAR_OPTIONS = Array.from({ length: 5 }, (_, i) => currentYear - i);

interface Props {
  accounts: AssetAccount[];
}

export default function TransactionHistoryTab({ accounts }: Props) {
  const qc = useQueryClient();
  const [selectedYear, setSelectedYear] = useState(currentYear);
  const [filterAccountId, setFilterAccountId] = useState("");
  const [filterType, setFilterType] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [depositPrompt, setDepositPrompt] = useState<{
    accountId: string;
    amount: number;
    txType: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
    currentDeposit: number;
  } | null>(null);

  const { data: txList = [], isLoading } = useQuery<Transaction[]>({
    queryKey: ["transactions", "all", selectedYear],
    queryFn: () => fetchTransactions({ year: selectedYear }),
  });

  const deleteMut = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: () => invalidateTransactionData(qc),
    onError: (e) => toast(extractErrorMessage(e, "내역 삭제에 실패했습니다"), "error"),
  });

  const triggerDepositPrompt = (accId: string, amt: number, txType: string) => {
    if (!accId || amt <= 0) return;
    const acc = accounts.find((a) => a.id === accId);
    if (!acc || !STOCK_TYPES.includes(acc.asset_type)) return;
    setDepositPrompt({
      accountId: accId,
      amount: amt,
      txType: txType as "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND",
      currentDeposit: acc.deposit_krw ?? 0,
    });
  };

  const startEdit = (tx: Transaction) => {
    setEditingTx(tx);
    setShowForm(true);
  };

  const handleFormSuccess = (accId: string, amount: number, txType: string) => {
    setShowForm(false);
    setEditingTx(null);
    triggerDepositPrompt(accId, amount, txType);
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingTx(null);
  };

  const yearDeposit = useMemo(
    () => txList.filter((t) => t.transaction_type === "DEPOSIT").reduce((s, t) => s + t.amount, 0),
    [txList],
  );
  const yearDividend = useMemo(
    () => txList.filter((t) => t.transaction_type === "DIVIDEND").reduce((s, t) => s + t.amount, 0),
    [txList],
  );

  const filtered = useMemo(
    () =>
      txList.filter((t) => {
        if (filterAccountId && t.account_id !== filterAccountId) return false;
        if (filterType && t.transaction_type !== filterType) return false;
        return true;
      }),
    [txList, filterAccountId, filterType],
  );

  const accountMap = useMemo(
    () => Object.fromEntries(accounts.map((a) => [a.id, a.name])),
    [accounts],
  );

  const tableContainerRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => tableContainerRef.current,
    estimateSize: () => 48,
    overscan: 10,
  });
  const virtualItems = rowVirtualizer.getVirtualItems();
  const paddingTop = virtualItems.length > 0 ? virtualItems[0].start : 0;
  const paddingBottom = virtualItems.length > 0
    ? rowVirtualizer.getTotalSize() - virtualItems[virtualItems.length - 1].end
    : 0;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="card">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{selectedYear}년 입금 합계</p>
          <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{fmtKrw(yearDeposit)}</p>
        </div>
        <div className="card">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{selectedYear}년 배당 합계</p>
          <p className="text-xl font-bold text-green-600 dark:text-green-400">{fmtKrw(yearDividend)}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select value={filterAccountId} onChange={(e) => setFilterAccountId(e.target.value)}
          className={INPUT_SM}>
          <option value="">전체 계좌</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
          className={INPUT_SM}>
          <option value="">전체 유형</option>
          <option value="DEPOSIT">입금</option>
          <option value="WITHDRAWAL">출금</option>
          <option value="DIVIDEND">배당</option>
        </select>
        <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))}
          className={INPUT_SM}>
          {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}년</option>)}
        </select>
        <button onClick={() => setShowForm((v) => !v)}
          className="ml-auto flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          {showForm ? <ChevronUp size={16} /> : <Plus size={16} />}
          내역 추가
        </button>
      </div>

      {showForm && (
        <TransactionForm
          key={editingTx?.id ?? "new"}
          accounts={accounts}
          editingTx={editingTx}
          onSuccess={handleFormSuccess}
          onCancel={handleFormCancel}
        />
      )}

      {depositPrompt && (
        <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-2xl p-4">
          <p className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-1">예수금에 반영할까요?</p>
          <p className="text-xs text-blue-600 dark:text-blue-400 mb-3">
            {fmtKrw(depositPrompt.currentDeposit)}
            {" → "}
            {fmtKrw(Math.max(0, depositPrompt.currentDeposit + (depositPrompt.txType === "WITHDRAWAL" ? -depositPrompt.amount : depositPrompt.amount)))}
            {" ("}
            {depositPrompt.txType === "WITHDRAWAL" ? "-" : "+"}
            {fmtKrw(depositPrompt.amount)}{")"}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => {
                const next = Math.max(0, depositPrompt.currentDeposit + (depositPrompt.txType === "WITHDRAWAL" ? -depositPrompt.amount : depositPrompt.amount));
                updateAccount(depositPrompt.accountId, { deposit_krw: next }).then(() => {
                  void invalidateAccountData(qc);
                });
                setDepositPrompt(null);
              }}
              className="px-4 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors"
            >
              반영
            </button>
            <button
              onClick={() => setDepositPrompt(null)}
              className="px-4 py-1.5 text-gray-500 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              건너뜀
            </button>
          </div>
        </div>
      )}

      <div className="card-overflow">
        {isLoading ? (
          <EmptyState title="불러오는 중..." compact />
        ) : filtered.length === 0 ? (
          <EmptyState title="등록된 내역이 없습니다." compact />
        ) : (
          <>
            {/* 모바일 카드 뷰 */}
            <div className="sm:hidden overflow-y-auto divide-y divide-gray-100 dark:divide-gray-700" style={{ maxHeight: "70vh" }}>
              {filtered.map((tx: Transaction) => (
                <div key={tx.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-medium ${TX_COLORS[tx.transaction_type]}`}>{TX_LABELS[tx.transaction_type]}</span>
                        {tx.ticker && <span className="text-xs text-gray-400 dark:text-gray-500">{tx.ticker}</span>}
                      </div>
                      <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                        {tx.transaction_date} · {tx.account_id ? (accountMap[tx.account_id] ?? "—") : "—"}
                      </p>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <p className="font-semibold text-gray-900 dark:text-gray-50 text-sm">{fmtKrw(tx.amount)}</p>
                      <button onClick={() => startEdit(tx)} aria-label="수정"
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => deleteMut.mutate(tx.id)} disabled={deleteMut.isPending} aria-label="삭제"
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  {tx.notes && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{tx.notes}</p>}
                </div>
              ))}
            </div>

            {/* 데스크탑 테이블 — 가상화 (패딩-행 방식으로 native 레이아웃 유지) */}
            <div
              ref={tableContainerRef}
              className="hidden sm:block overflow-auto"
              style={{ maxHeight: "640px" }}
            >
              <table className="w-full text-sm">
                <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
                  <tr className="border-b border-gray-100 dark:border-gray-700">
                    <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">날짜</th>
                    <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">구분</th>
                    <th className="text-right px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">금액</th>
                    <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">계좌</th>
                    <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">메모</th>
                    <th className="px-3 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {paddingTop > 0 && <tr><td colSpan={6} style={{ height: paddingTop }} /></tr>}
                  {virtualItems.map((virtualRow) => {
                    const tx = filtered[virtualRow.index];
                    return (
                      <tr key={tx.id} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                        <td className="px-3 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap text-xs">{tx.transaction_date}</td>
                        <td className={`px-3 py-3 font-medium whitespace-nowrap ${TX_COLORS[tx.transaction_type]}`}>
                          <span>{TX_LABELS[tx.transaction_type]}</span>
                          {tx.ticker && <span className="block text-xs text-gray-400 dark:text-gray-500 font-normal mt-0.5">{tx.ticker}</span>}
                        </td>
                        <td className="px-3 py-3 text-right font-semibold text-gray-900 dark:text-gray-50 whitespace-nowrap">{fmtKrw(tx.amount)}</td>
                        <td className="px-3 py-3 text-gray-500 dark:text-gray-400 text-xs whitespace-nowrap">
                          {tx.account_id ? (accountMap[tx.account_id] ?? "—") : "—"}
                        </td>
                        <td className="px-3 py-3 text-gray-400 dark:text-gray-500 text-sm">
                          <div className="max-w-[160px] truncate">{tx.notes || "—"}</div>
                        </td>
                        <td className="px-3 py-3 text-right">
                          <div className="flex justify-end gap-1">
                            <button onClick={() => startEdit(tx)} aria-label="수정"
                              className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
                              <Pencil size={15} />
                            </button>
                            <button onClick={() => deleteMut.mutate(tx.id)} disabled={deleteMut.isPending} aria-label="삭제"
                              className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors">
                              <Trash2 size={15} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {paddingBottom > 0 && <tr><td colSpan={6} style={{ height: paddingBottom }} /></tr>}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
