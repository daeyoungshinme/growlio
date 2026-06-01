import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, X } from "lucide-react";
import { useState } from "react";
import Modal from "../common/Modal";
import { api } from "../../api/client";
import { useExchangeRate } from "../../hooks/useExchangeRate";
import { useForm } from "../../hooks/useForm";
import { useStockSearch } from "../../hooks/useStockSearch";
import {
  createTransaction,
  deleteTransaction,
  fetchTransactions,
  Transaction,
  TransactionCreate,
  updateTransaction,
} from "../../api/transactions";
import { fmtKrw } from "../../utils/format";
import { invalidateTransactionData } from "../../utils/queryInvalidation";
import { toast } from "../../utils/toast";
import { TX_LABELS, TX_COLORS } from "../../constants/transaction";
import { STALE_TIME } from "../../constants/queryConfig";

interface Props {
  accountId: string;
  accountName: string;
  depositKrw?: number;
  onDepositUpdate?: (newDeposit: number) => void;
  onClose: () => void;
}

const today = new Date().toISOString().slice(0, 10);

const EMPTY_FORM: TransactionCreate = {
  account_id: "",
  transaction_type: "DEPOSIT",
  amount: 0,
  transaction_date: today,
  ticker: "",
  notes: "",
};

export default function TransactionModal({ accountId, accountName, depositKrw = 0, onDepositUpdate, onClose }: Props) {
  const qc = useQueryClient();
  const { form, set, setForm } = useForm<TransactionCreate>({ ...EMPTY_FORM, account_id: accountId });

  const [currency, setCurrency] = useState<"KRW" | "USD">("KRW");
  const [amountUsd, setAmountUsd] = useState<number>(0);
  const usdRate = useExchangeRate();
  const [tickerDirect, setTickerDirect] = useState(false);
  const [tickerQuery, setTickerQuery] = useState("");
  const { suggestions: tickerSuggestions, isSearching: tickerSearchLoading, search: runTickerSearch, clearSuggestions: clearTickerSuggestions } = useStockSearch();
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [depositPrompt, setDepositPrompt] = useState<{
    amount: number;
    txType: "DEPOSIT" | "WITHDRAWAL" | "DIVIDEND";
  } | null>(null);

  const { data: txList, isLoading } = useQuery<Transaction[]>({
    queryKey: ["transactions", accountId],
    queryFn: () => fetchTransactions({ account_id: accountId }),
  });

  const { data: positionsData } = useQuery<{ positions: Array<{ ticker: string; name: string; qty: number }> }>({
    queryKey: ["account-positions", accountId],
    queryFn: () =>
      api
        .get<{ positions: Array<{ ticker: string; name: string; qty: number }> }>(`/assets/${accountId}/positions`)
        .then((r) => r.data),
    enabled: !!accountId,
    staleTime: STALE_TIME.MEDIUM,
  });
  const accountPositions = positionsData?.positions ?? [];

  const invalidate = () => invalidateTransactionData(qc);

  const resetForm = () => {
    setForm({ ...EMPTY_FORM, account_id: accountId });
    setCurrency("KRW"); setAmountUsd(0);
    setTickerDirect(false); setTickerQuery(""); clearTickerSuggestions(); setShowTickerSuggestions(false);
  };

  const VALID_TX_TYPES = ["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const;
  type TxType = (typeof VALID_TX_TYPES)[number];
  const isValidTxType = (val: unknown): val is TxType =>
    VALID_TX_TYPES.includes(val as TxType);

  const triggerDepositPrompt = (amt: number, txType: string) => {
    if (amt > 0 && onDepositUpdate && isValidTxType(txType)) {
      setDepositPrompt({ amount: amt, txType });
    }
  };

  const createMut = useMutation({
    mutationFn: createTransaction,
    onSuccess: (_, vars) => {
      invalidate();
      const amt = vars.amount ?? 0;
      const txType = vars.transaction_type;
      resetForm();
      triggerDepositPrompt(amt, txType);
    },
    onError: () => toast("내역 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TransactionCreate> }) =>
      updateTransaction(id, data),
    onSuccess: (_, vars) => {
      invalidate();
      const amt = vars.data?.amount ?? 0;
      const txType = vars.data?.transaction_type ?? "";
      setEditingTx(null);
      resetForm();
      triggerDepositPrompt(amt, txType);
    },
    onError: () => toast("내역 수정에 실패했습니다"),
  });

  const deleteMut = useMutation({
    mutationFn: deleteTransaction,
    onSuccess: invalidate,
    onError: () => toast("내역 삭제에 실패했습니다"),
  });

  const startEdit = (tx: Transaction) => {
    setEditingTx(tx);
    setForm({
      account_id: accountId,
      transaction_type: tx.transaction_type,
      amount: tx.amount,
      transaction_date: tx.transaction_date,
      ticker: tx.ticker ?? "",
      notes: tx.notes ?? "",
    });
    setTickerDirect(!!tx.ticker);
    setTickerQuery(tx.ticker ?? "");
    setCurrency("KRW"); setAmountUsd(0);
    clearTickerSuggestions(); setShowTickerSuggestions(false);
  };

  const handleSubmit = () => {
    if (!form.amount || form.amount <= 0) return;
    const payload = {
      ...form,
      ticker: form.transaction_type === "DIVIDEND" && form.ticker ? form.ticker : undefined,
      notes: form.notes || undefined,
    };
    if (editingTx) {
      updateMut.mutate({ id: editingTx.id, data: payload });
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
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors">
            <X size={18} className="text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* 추가 폼 */}
        <div className="px-6 py-4 border-b border-gray-100 dark:border-gray-700 space-y-3 shrink-0">
          {/* 유형 */}
          <div className="flex gap-2">
            {(["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const).map((t) => (
              <button
                key={t}
                onClick={() => {
                  set("transaction_type", t);
                  setCurrency("KRW"); setAmountUsd(0);
                  setTickerDirect(false); setTickerQuery(""); clearTickerSuggestions(); setShowTickerSuggestions(false);
                }}
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
                    {(["KRW", "USD"] as const).map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => {
                          if (c === currency) return;
                          if (c === "USD") {
                            setAmountUsd(usdRate && form.amount ? parseFloat((form.amount / usdRate).toFixed(2)) : 0);
                          } else {
                            setAmountUsd(0);
                          }
                          setCurrency(c);
                        }}
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
                      onChange={(e) => {
                        const usd = parseFloat(e.target.value) || 0;
                        setAmountUsd(usd);
                        set("amount", usdRate ? Math.round(usd * usdRate) : 0);
                      }}
                      placeholder="0.00"
                      step="0.01"
                      min={0}
                    />
                  </div>
                  {usdRate && amountUsd > 0 && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                      ≈ ₩{Math.round(amountUsd * usdRate).toLocaleString()}
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
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400">날짜 *</label>
              </div>
              <input
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
              <label className="text-xs font-medium text-gray-600 dark:text-gray-400">종목 (선택)</label>
              {accountPositions.length > 0 && !tickerDirect ? (
                <select
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={form.ticker || ""}
                  onChange={(e) => {
                    if (e.target.value === "__direct__") {
                      setTickerDirect(true); set("ticker", "");
                    } else {
                      set("ticker", e.target.value);
                    }
                  }}
                >
                  <option value="">종목 선택</option>
                  {accountPositions.map((p) => (
                    <option key={p.ticker} value={p.name}>{p.name}</option>
                  ))}
                  <option value="__direct__">기타 종목 직접 입력...</option>
                </select>
              ) : (
                <div className="flex gap-1 mt-1">
                  <div className="relative w-full">
                    <input
                      value={tickerQuery}
                      onChange={(e) => {
                        const v = e.target.value;
                        setTickerQuery(v); set("ticker", v);
                        setShowTickerSuggestions(true);
                        if (!v.trim()) { clearTickerSuggestions(); return; }
                        runTickerSearch(v);
                      }}
                      onFocus={() => tickerSuggestions.length > 0 && setShowTickerSuggestions(true)}
                      onBlur={() => setTimeout(() => setShowTickerSuggestions(false), 150)}
                      placeholder="종목명 또는 코드 검색"
                      className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    {tickerSearchLoading && (
                      <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">검색 중...</span>
                    )}
                    {showTickerSuggestions && tickerSuggestions.length > 0 && (
                      <ul className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-40 overflow-y-auto">
                        {tickerSuggestions.map((s) => (
                          <li key={s.ticker}
                            className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2"
                            onMouseDown={() => {
                              setTickerQuery(s.name); set("ticker", s.name);
                              clearTickerSuggestions(); setShowTickerSuggestions(false);
                            }}>
                            <span className="font-medium text-blue-700 dark:text-blue-400">{s.ticker}</span>
                            <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
                            <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">{s.market}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {accountPositions.length > 0 && (
                    <button type="button"
                      onClick={() => { setTickerDirect(false); set("ticker", ""); setTickerQuery(""); clearTickerSuggestions(); setShowTickerSuggestions(false); }}
                      className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap">
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
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">보유 종목 참고</p>
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
                      <tr key={p.ticker}
                        className="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-white dark:hover:bg-gray-700 transition-colors"
                        onClick={() => { set("ticker", p.name); setTickerDirect(false); setTickerQuery(""); }}>
                        <td className="py-1 text-gray-700 dark:text-gray-300">{p.name}</td>
                        <td className="py-1 text-right text-gray-500 dark:text-gray-400">{p.qty?.toLocaleString() ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 메모 */}
          <div>
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400">메모 (선택)</label>
            <input
              className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.notes || ""}
              onChange={(e) => set("notes", e.target.value)}
              placeholder="메모 입력"
            />
          </div>

          <button
            onClick={handleSubmit}
            disabled={(editingTx ? updateMut.isPending : createMut.isPending) || !form.amount}
            className="w-full py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {(editingTx ? updateMut.isPending : createMut.isPending) ? "저장 중..." : editingTx ? "수정" : "내역 추가"}
          </button>
        </div>

        {/* 예수금 반영 확인 팝업 */}
        {depositPrompt && onDepositUpdate && (
          <div className="mx-6 mb-1 bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
            <p className="text-xs font-medium text-blue-800 dark:text-blue-300 mb-1">예수금에 반영할까요?</p>
            <p className="text-xs text-blue-600 dark:text-blue-400 mb-2">
              {fmtKrw(depositKrw)}
              {" → "}
              {fmtKrw(Math.max(0, depositKrw + (depositPrompt.txType === "WITHDRAWAL" ? -depositPrompt.amount : depositPrompt.amount)))}
              {" ("}
              {depositPrompt.txType === "WITHDRAWAL" ? "-" : "+"}
              {fmtKrw(depositPrompt.amount)}{")"}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  const next = Math.max(0, depositKrw + (depositPrompt.txType === "WITHDRAWAL" ? -depositPrompt.amount : depositPrompt.amount));
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
          {(() => {
            const filtered = (txList ?? []).filter((t) =>
              t.transaction_type === form.transaction_type
            );
            return isLoading ? (
              <div className="py-8 text-center text-gray-300 dark:text-gray-600 text-sm">로딩 중...</div>
            ) : filtered.length === 0 ? (
              <div className="py-8 text-center text-gray-300 dark:text-gray-600 text-sm">등록된 내역이 없습니다</div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                    <th className="text-left px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">날짜</th>
                    <th className="text-left px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">구분</th>
                    <th className="text-right px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">금액</th>
                    <th className="text-left px-3 py-2.5 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">메모</th>
                    <th className="px-3 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                {filtered.map((tx) => (
                  <tr key={tx.id} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <td className="px-3 py-3 text-gray-500 dark:text-gray-400 whitespace-nowrap text-xs">{tx.transaction_date}</td>
                    <td className={`px-3 py-3 font-medium whitespace-nowrap ${TX_COLORS[tx.transaction_type]}`}>
                      <span>{TX_LABELS[tx.transaction_type]}</span>
                      {tx.ticker && <span className="block text-xs text-gray-400 dark:text-gray-500 font-normal mt-0.5">{tx.ticker}</span>}
                    </td>
                    <td className="px-3 py-3 text-right font-semibold text-gray-900 dark:text-gray-50 whitespace-nowrap">
                      {fmtKrw(tx.amount)}
                    </td>
                    <td className="px-3 py-3 text-gray-400 dark:text-gray-500 text-xs">
                      <div className="max-w-[100px] truncate">{tx.notes || "—"}</div>
                    </td>
                    <td className="px-3 py-3 text-right">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => startEdit(tx)}
                          className="p-1 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors"
                        >
                          <Pencil size={13} />
                        </button>
                        <button
                          onClick={() => deleteMut.mutate(tx.id)}
                          disabled={deleteMut.isPending}
                          className="p-1 text-gray-300 dark:text-gray-600 hover:text-red-400 transition-colors"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        })()}
        </div>
    </Modal>
  );
}
