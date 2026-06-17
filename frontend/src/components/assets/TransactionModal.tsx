import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import Modal from "@/components/common/Modal";
import { api } from "@/api/client";
import {
  createTransaction,
  deleteTransaction,
  fetchTransactions,
  Transaction,
  updateTransaction,
} from "@/api/transactions";
import { convertUsdToKrw, fmtKrw } from "@/utils/format";
import { invalidateTransactionData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { TX_LABELS, TX_TYPES, CURRENCY_TYPES } from "@/constants/transaction";
import { TransactionList } from "./TransactionList";
import { STALE_TIME } from "@/constants/queryConfig";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { SEARCH_DROPDOWN_HIDE_DELAY } from "@/constants/timers";
import { transactionSchema } from "@/schemas/transaction";
import { useTransactionFormState } from "@/hooks/useTransactionFormState";

interface Props {
  accountId: string;
  accountName: string;
  depositKrw?: number;
  onDepositUpdate?: (newDeposit: number) => void;
  onClose: () => void;
}

export default function TransactionModal({
  accountId,
  accountName,
  depositKrw = 0,
  onDepositUpdate,
  onClose,
}: Props) {
  const qc = useQueryClient();
  const {
    form,
    set,
    formError,
    setFormError,
    currency,
    amountUsd,
    usdRate,
    tickerDirect,
    setTickerDirect,
    tickerQuery,
    tickerSuggestions,
    tickerSearchLoading,
    showTickerSuggestions,
    setShowTickerSuggestions,
    clearTickerSuggestions,
    editingTx,
    setEditingTx,
    depositPrompt,
    setDepositPrompt,
    resetForm,
    startEdit,
    triggerDepositPrompt,
    handleCurrencySwitch,
    handleUsdAmountChange,
    handleTxTypeChange,
    handleTickerQueryChange,
  } = useTransactionFormState(accountId);

  const { data: txList, isLoading } = useQuery<Transaction[]>({
    queryKey: QUERY_KEYS.transactions(accountId),
    queryFn: () => fetchTransactions({ account_id: accountId }),
  });

  const { data: positionsData } = useQuery<{
    positions: Array<{ ticker: string; name: string; qty: number }>;
  }>({
    queryKey: QUERY_KEYS.accountPositions(accountId),
    queryFn: () =>
      api
        .get<{
          positions: Array<{ ticker: string; name: string; qty: number }>;
        }>(`/assets/${accountId}/positions`)
        .then((r) => r.data),
    enabled: !!accountId,
    staleTime: STALE_TIME.MEDIUM,
  });
  const accountPositions = positionsData?.positions ?? [];

  const invalidate = () => invalidateTransactionData(qc);

  const createMut = useMutation({
    mutationFn: createTransaction,
    onSuccess: (_, vars) => {
      invalidate();
      resetForm();
      triggerDepositPrompt(vars.amount ?? 0, vars.transaction_type);
    },
    onError: () => toast("내역 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateTransaction>[1] }) =>
      updateTransaction(id, data),
    onSuccess: (_, vars) => {
      invalidate();
      setEditingTx(null);
      resetForm();
      triggerDepositPrompt(vars.data?.amount ?? 0, vars.data?.transaction_type ?? "");
    },
    onError: () => toast("내역 수정에 실패했습니다"),
  });

  const deleteMut = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: invalidate,
    onError: () => toast("내역 삭제에 실패했습니다"),
  });

  const handleSubmit = () => {
    const result = transactionSchema.safeParse({
      transaction_type: form.transaction_type,
      amount: form.amount,
      transaction_date: form.transaction_date,
      ticker: form.ticker || undefined,
      notes: form.notes || undefined,
    });
    if (!result.success) {
      setFormError(result.error.issues[0]?.message ?? "입력값을 확인해주세요");
      return;
    }
    setFormError(null);
    const payload = {
      ...form,
      ticker: form.transaction_type === "DIVIDEND" && form.ticker ? form.ticker : undefined,
      notes: form.notes || undefined,
    };
    if (editingTx) {
      updateMut.mutate({
        id: editingTx.id,
        data: payload as Parameters<typeof updateTransaction>[1],
      });
    } else {
      createMut.mutate(payload);
    }
  };

  return (
    <Modal size="md" onClose={onClose}>
      {/* 헤더 */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-700 shrink-0">
        <div>
          <h2 className="text-base font-bold text-gray-900 dark:text-gray-50">입출금 내역</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{accountName}</p>
        </div>
        <button
          onClick={onClose}
          aria-label="닫기"
          className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
        >
          <X size={18} aria-hidden="true" className="text-gray-500 dark:text-gray-400" />
        </button>
      </div>

      {/* 추가 폼 */}
      <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 space-y-3 shrink-0">
        {/* 유형 */}
        <div className="flex gap-2">
          {TX_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => handleTxTypeChange(t)}
              className={`flex-1 py-2 text-sm font-medium rounded-lg border transition-colors ${
                form.transaction_type === t
                  ? "bg-blue-600 text-white border-blue-600"
                  : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-300"
              }`}
            >
              {TX_LABELS[t]}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          {/* 금액 */}
          <div>
            <div className="flex items-center justify-between h-5">
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400">금액 *</label>
              {form.transaction_type === "DIVIDEND" && (
                <div className="flex gap-0.5 text-xs">
                  {CURRENCY_TYPES.map((c) => (
                    <button
                      key={c}
                      type="button"
                      onClick={() => handleCurrencySwitch(c)}
                      className={`px-1.5 py-0.5 rounded transition-colors ${
                        currency === c
                          ? "bg-blue-600 text-white"
                          : "text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                      }`}
                    >
                      {c}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {currency === "USD" && form.transaction_type === "DIVIDEND" ? (
              <div>
                <div className="flex items-center gap-1.5 mt-1">
                  <span className="text-sm text-gray-400 shrink-0">$</span>
                  <input
                    type="number"
                    className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    value={amountUsd || ""}
                    onChange={(e) => handleUsdAmountChange(parseFloat(e.target.value) || 0)}
                    placeholder="0.00"
                    step="0.01"
                    min={0}
                  />
                </div>
                {convertUsdToKrw(amountUsd, usdRate) > 0 && (
                  <p className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                    ≈ ₩{convertUsdToKrw(amountUsd, usdRate).toLocaleString()}
                  </p>
                )}
              </div>
            ) : (
              <input
                type="number"
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.amount || ""}
                onChange={(e) => set("amount", Number(e.target.value))}
                placeholder="예: 500000"
                min={0}
              />
            )}
          </div>
          {/* 날짜 */}
          <div className="min-w-0">
            <div className="flex items-center h-5">
              <label
                htmlFor="tx-date"
                className="text-xs font-medium text-gray-600 dark:text-gray-400"
              >
                날짜 *
              </label>
            </div>
            <input
              id="tx-date"
              type="date"
              className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.transaction_date}
              onChange={(e) => set("transaction_date", e.target.value)}
            />
          </div>
        </div>

        {/* 종목 (배당 전용) */}
        {form.transaction_type === "DIVIDEND" && (
          <div>
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">
              종목 (선택)
            </label>
            {accountPositions.length > 0 && !tickerDirect ? (
              <select
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.ticker || ""}
                onChange={(e) => {
                  if (e.target.value === "__direct__") {
                    setTickerDirect(true);
                    set("ticker", "");
                  } else {
                    set("ticker", e.target.value);
                  }
                }}
              >
                <option value="">종목 선택</option>
                {accountPositions.map((p) => (
                  <option key={p.ticker} value={p.name}>
                    {p.name}
                  </option>
                ))}
                <option value="__direct__">기타 종목 직접 입력...</option>
              </select>
            ) : (
              <div className="flex gap-1 mt-1">
                <div className="relative w-full">
                  <input
                    value={tickerQuery}
                    onChange={(e) => handleTickerQueryChange(e.target.value)}
                    onFocus={() => tickerSuggestions.length > 0 && setShowTickerSuggestions(true)}
                    onBlur={() =>
                      setTimeout(() => setShowTickerSuggestions(false), SEARCH_DROPDOWN_HIDE_DELAY)
                    }
                    placeholder="종목명 또는 코드 검색"
                    className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {tickerSearchLoading && (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                      검색 중...
                    </span>
                  )}
                  {showTickerSuggestions && tickerSuggestions.length > 0 && (
                    <ul className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-40 overflow-y-auto">
                      {tickerSuggestions.map((s) => (
                        <li
                          key={s.ticker}
                          className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2"
                          onMouseDown={() => {
                            handleTickerQueryChange(s.name);
                            set("ticker", s.name);
                            clearTickerSuggestions();
                            setShowTickerSuggestions(false);
                          }}
                        >
                          <span className="font-medium text-blue-700 dark:text-blue-400">
                            {s.ticker}
                          </span>
                          <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
                          <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">
                            {s.market}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                {accountPositions.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setTickerDirect(false);
                      set("ticker", "");
                      handleTickerQueryChange("");
                    }}
                    className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap"
                  >
                    ← 목록
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* 보유 종목 참고 */}
        {form.transaction_type === "DIVIDEND" && accountPositions.length > 0 && (
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
              보유 종목 참고
            </p>
            <div className="max-h-28 overflow-y-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-400 dark:text-gray-500">
                    <th className="text-left pb-1">종목명</th>
                    <th className="text-right pb-1">수량</th>
                  </tr>
                </thead>
                <tbody>
                  {accountPositions.map((p) => (
                    <tr
                      key={p.ticker}
                      className="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-white dark:hover:bg-gray-700 transition-colors"
                      onClick={() => {
                        set("ticker", p.name);
                        setTickerDirect(false);
                        handleTickerQueryChange("");
                      }}
                    >
                      <td className="py-1 text-gray-700 dark:text-gray-300">{p.name}</td>
                      <td className="py-1 text-right text-gray-500 dark:text-gray-400">
                        {p.qty?.toLocaleString() ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 메모 */}
        <div>
          <label
            htmlFor="tx-notes"
            className="text-xs font-medium text-gray-600 dark:text-gray-400"
          >
            메모 (선택)
          </label>
          <input
            id="tx-notes"
            className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={form.notes || ""}
            onChange={(e) => set("notes", e.target.value)}
            placeholder="메모 입력"
          />
        </div>

        {formError && (
          <p role="alert" className="text-xs text-red-500 dark:text-red-400">
            {formError}
          </p>
        )}
        <button
          onClick={handleSubmit}
          disabled={editingTx ? updateMut.isPending : createMut.isPending}
          aria-busy={editingTx ? updateMut.isPending : createMut.isPending}
          className="w-full py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {(editingTx ? updateMut.isPending : createMut.isPending)
            ? "저장 중..."
            : editingTx
              ? "수정"
              : "내역 추가"}
        </button>
      </div>

      {/* 예수금 반영 확인 팝업 */}
      {depositPrompt && onDepositUpdate && (
        <div className="mx-6 mb-1 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
          <p className="text-xs font-medium text-blue-800 dark:text-blue-300 mb-1">
            예수금에 반영할까요?
          </p>
          <p className="text-xs text-blue-600 dark:text-blue-400 mb-2">
            {fmtKrw(depositKrw)}
            {" → "}
            {fmtKrw(
              Math.max(
                0,
                depositKrw +
                  (depositPrompt.txType === "WITHDRAWAL"
                    ? -depositPrompt.amount
                    : depositPrompt.amount),
              ),
            )}
            {" ("}
            {depositPrompt.txType === "WITHDRAWAL" ? "-" : "+"}
            {fmtKrw(depositPrompt.amount)}
            {")"}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => {
                const next = Math.max(
                  0,
                  depositKrw +
                    (depositPrompt.txType === "WITHDRAWAL"
                      ? -depositPrompt.amount
                      : depositPrompt.amount),
                );
                onDepositUpdate(next);
                setDepositPrompt(null);
              }}
              className="px-3 py-1 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 transition-colors"
            >
              반영
            </button>
            <button
              onClick={() => setDepositPrompt(null)}
              className="px-3 py-1 text-gray-500 dark:text-gray-400 text-xs rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              건너뜀
            </button>
          </div>
        </div>
      )}

      {/* 내역 목록 */}
      <div className="overflow-y-auto flex-1">
        <TransactionList
          txList={txList}
          isLoading={isLoading}
          activeType={form.transaction_type}
          isDeleting={deleteMut.isPending}
          onEdit={startEdit}
          onDelete={(id) => deleteMut.mutate(id)}
        />
      </div>
    </Modal>
  );
}
