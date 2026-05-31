import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ChevronUp, Pencil, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import {
  searchStocks,
  updateAccount,
  type StockSuggestion,
  type AssetAccount,
} from "../../api/assets";
import { useExchangeRate } from "../../hooks/useExchangeRate";
import {
  fetchTransactions,
  createTransaction,
  updateTransaction,
  deleteTransaction,
  type Transaction,
  type TransactionCreate,
} from "../../api/transactions";
import { fmtKrw } from "../../utils/format";
import { invalidateAccountData, invalidateTransactionData } from "../../utils/queryInvalidation";
import { toast } from "../../utils/toast";
import { STOCK_TYPES } from "../../constants";
import { TX_LABELS, TX_COLORS } from "../../constants/transaction";
import { STALE_TIME } from "../../constants/queryConfig";

const today = new Date().toISOString().slice(0, 10);
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
  const [form, setForm] = useState<TransactionCreate>({
    account_id: "",
    transaction_type: "DEPOSIT",
    amount: 0,
    transaction_date: today,
    ticker: "",
    notes: "",
  });

  const [currency, setCurrency] = useState<"KRW" | "USD">("KRW");
  const [amountUsd, setAmountUsd] = useState<number>(0);
  const usdRate = useExchangeRate();
  const [tickerDirect, setTickerDirect] = useState(false);
  const [tickerQuery, setTickerQuery] = useState("");
  const [tickerSuggestions, setTickerSuggestions] = useState<StockSuggestion[]>([]);
  const [tickerSearchLoading, setTickerSearchLoading] = useState(false);
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);
  const tickerSearchTimer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    return () => { clearTimeout(tickerSearchTimer.current); };
  }, []);

  const { data: txList = [], isLoading } = useQuery<Transaction[]>({
    queryKey: ["transactions", "all", selectedYear],
    queryFn: () => fetchTransactions({ year: selectedYear }),
  });

  const { data: positionsData } = useQuery<{ positions: Array<{ ticker: string; name: string; qty: number }> }>({
    queryKey: ["account-positions", form.account_id],
    queryFn: () =>
      api
        .get<{ positions: Array<{ ticker: string; name: string; qty: number }> }>(
          `/assets/${form.account_id}/positions`
        )
        .then((r) => r.data),
    enabled: !!form.account_id && form.transaction_type === "DIVIDEND",
    staleTime: STALE_TIME.MEDIUM,
  });
  const accountPositions = positionsData?.positions ?? [];

  const invalidate = () => invalidateTransactionData(qc);

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

  const createMut = useMutation({
    mutationFn: createTransaction,
    onSuccess: (_, vars) => {
      invalidate();
      const accId = vars.account_id as string ?? "";
      const amt = vars.amount ?? 0;
      const txType = vars.transaction_type;
      setForm({ account_id: "", transaction_type: "DEPOSIT", amount: 0, transaction_date: today, ticker: "", notes: "" });
      setCurrency("KRW");
      setAmountUsd(0);
      setTickerDirect(false);
      setTickerQuery("");
      setTickerSuggestions([]);
      setShowTickerSuggestions(false);
      setShowForm(false);
      triggerDepositPrompt(accId, amt, txType);
    },
    onError: () => toast("내역 저장에 실패했습니다"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TransactionCreate> }) =>
      updateTransaction(id, data),
    onSuccess: (_, vars) => {
      invalidate();
      const accId = vars.data?.account_id as string ?? "";
      const amt = vars.data?.amount ?? 0;
      const txType = vars.data?.transaction_type ?? "";
      setEditingTx(null);
      setForm({ account_id: "", transaction_type: "DEPOSIT", amount: 0, transaction_date: today, ticker: "", notes: "" });
      setCurrency("KRW");
      setAmountUsd(0);
      setTickerDirect(false);
      setTickerQuery("");
      setTickerSuggestions([]);
      setShowTickerSuggestions(false);
      setShowForm(false);
      triggerDepositPrompt(accId, amt, txType);
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
      account_id: tx.account_id ?? "",
      transaction_type: tx.transaction_type,
      amount: tx.amount,
      transaction_date: tx.transaction_date,
      ticker: tx.ticker ?? "",
      notes: tx.notes ?? "",
    });
    setTickerDirect(!!tx.ticker);
    setTickerQuery(tx.ticker ?? "");
    setCurrency("KRW");
    setAmountUsd(0);
    setTickerSuggestions([]);
    setShowTickerSuggestions(false);
    setShowForm(true);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.amount || form.amount <= 0) return;
    const payload = {
      ...form,
      account_id: form.account_id || undefined,
      ticker: form.transaction_type === "DIVIDEND" && form.ticker ? form.ticker : undefined,
      notes: form.notes || undefined,
    };
    if (editingTx) {
      updateMut.mutate({ id: editingTx.id, data: payload });
    } else {
      createMut.mutate(payload);
    }
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
    () => txList.filter((t) => {
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

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{selectedYear}년 입금 합계</p>
          <p className="text-xl font-bold text-blue-600 dark:text-blue-400">{fmtKrw(yearDeposit)}</p>
        </div>
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">{selectedYear}년 배당 합계</p>
          <p className="text-xl font-bold text-green-600 dark:text-green-400">{fmtKrw(yearDividend)}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select value={filterAccountId} onChange={(e) => setFilterAccountId(e.target.value)}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">전체 계좌</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <select value={filterType} onChange={(e) => setFilterType(e.target.value)}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          <option value="">전체 유형</option>
          <option value="DEPOSIT">입금</option>
          <option value="WITHDRAWAL">출금</option>
          <option value="DIVIDEND">배당</option>
        </select>
        <select value={selectedYear} onChange={(e) => setSelectedYear(Number(e.target.value))}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
          {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}년</option>)}
        </select>
        <button onClick={() => setShowForm((v) => !v)}
          className="ml-auto flex items-center gap-1.5 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors">
          {showForm ? <ChevronUp size={16} /> : <Plus size={16} />}
          내역 추가
        </button>
      </div>

      {showForm && (
        <form onSubmit={handleSubmit} className={`bg-white dark:bg-gray-900 rounded-2xl border p-5 space-y-4 ${editingTx ? "border-amber-200 dark:border-amber-800" : "border-blue-200 dark:border-blue-800"}`}>
          <div className="flex gap-2">
            {(["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const).map((t) => (
              <button key={t} type="button"
                onClick={() => { setForm((f) => ({ ...f, transaction_type: t })); setCurrency("KRW"); setAmountUsd(0); setTickerDirect(false); setTickerQuery(""); setTickerSuggestions([]); setShowTickerSuggestions(false); }}
                className={`flex-1 py-2 text-sm font-medium rounded-lg border transition-colors ${
                  form.transaction_type === t
                    ? "bg-blue-600 text-white border-blue-600"
                    : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-300 dark:hover:border-blue-600"
                }`}>
                {TX_LABELS[t]}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">계좌 선택</label>
              <select value={form.account_id}
                onChange={(e) => { setForm((f) => ({ ...f, account_id: e.target.value, ticker: "" })); setTickerDirect(false); setTickerQuery(""); setTickerSuggestions([]); setShowTickerSuggestions(false); }}
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">계좌 미지정</option>
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">날짜 *</label>
              <input type="date" required value={form.transaction_date}
                onChange={(e) => setForm((f) => ({ ...f, transaction_date: e.target.value }))}
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">금액 *</label>
                {form.transaction_type === "DIVIDEND" && (
                  <div className="flex gap-0.5 text-xs">
                    {(["KRW", "USD"] as const).map((c) => (
                      <button key={c} type="button"
                        onClick={() => { setCurrency(c); setAmountUsd(0); }}
                        className={`px-1.5 py-0.5 rounded transition-colors ${
                          currency === c ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-600"
                        }`}>
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
                    <input type="number"
                      value={amountUsd || ""}
                      onChange={(e) => {
                        const usd = parseFloat(e.target.value) || 0;
                        setAmountUsd(usd);
                        setForm((f) => ({ ...f, amount: usdRate ? Math.round(usd * usdRate) : f.amount }));
                      }}
                      placeholder="0.00" step="0.01" min={0}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
                  </div>
                  {usdRate && amountUsd > 0 && (
                    <p className="text-xs text-gray-400 text-right mt-0.5">
                      ≈ ₩{Math.round(amountUsd * usdRate).toLocaleString()}
                    </p>
                  )}
                  {!usdRate && currency === "USD" && (
                    <p className="text-xs text-amber-500 mt-0.5">환율 정보를 불러오는 중입니다</p>
                  )}
                </div>
              ) : (
                <input type="number" required min={1} value={form.amount || ""}
                  onChange={(e) => setForm((f) => ({ ...f, amount: Number(e.target.value) }))}
                  placeholder="예: 500000"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              )}
            </div>
            {form.transaction_type === "DIVIDEND" ? (
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">종목 (선택)</label>
                {accountPositions.length > 0 && !tickerDirect ? (
                  <select
                    value={form.ticker || ""}
                    onChange={(e) => {
                      if (e.target.value === "__direct__") {
                        setTickerDirect(true);
                        setForm((f) => ({ ...f, ticker: "" }));
                      } else {
                        setForm((f) => ({ ...f, ticker: e.target.value }));
                      }
                    }}
                    className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">종목 선택</option>
                    {accountPositions.map((p) => (
                      <option key={p.ticker} value={p.ticker}>{p.name}</option>
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
                          setTickerQuery(v);
                          setForm((f) => ({ ...f, ticker: v }));
                          setShowTickerSuggestions(true);
                          if (tickerSearchTimer.current) clearTimeout(tickerSearchTimer.current);
                          if (!v.trim()) { setTickerSuggestions([]); return; }
                          tickerSearchTimer.current = setTimeout(async () => {
                            setTickerSearchLoading(true);
                            try { setTickerSuggestions(await searchStocks(v.trim())); }
                            catch { setTickerSuggestions([]); }
                            finally { setTickerSearchLoading(false); }
                          }, 300);
                        }}
                        onFocus={() => tickerSuggestions.length > 0 && setShowTickerSuggestions(true)}
                        onBlur={() => setTimeout(() => setShowTickerSuggestions(false), 150)}
                        placeholder="종목명 또는 코드 검색"
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      {tickerSearchLoading && (
                        <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 dark:text-gray-500">검색 중...</span>
                      )}
                      {showTickerSuggestions && tickerSuggestions.length > 0 && (
                        <ul className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-48 overflow-y-auto">
                          {tickerSuggestions.map((s) => (
                            <li key={s.ticker}
                              className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2"
                              onMouseDown={() => {
                                setTickerQuery(s.name);
                                setForm((f) => ({ ...f, ticker: s.ticker }));
                                setTickerSuggestions([]);
                                setShowTickerSuggestions(false);
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
                        onClick={() => { setTickerDirect(false); setForm((f) => ({ ...f, ticker: "" })); setTickerQuery(""); setTickerSuggestions([]); setShowTickerSuggestions(false); }}
                        className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap">
                        ← 목록
                      </button>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <label className="text-sm font-medium text-gray-700 dark:text-gray-300">메모 (선택)</label>
                <input value={form.notes || ""}
                  onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="메모 입력"
                  className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
            )}
          </div>
          {form.transaction_type === "DIVIDEND" && (
            <div>
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">메모 (선택)</label>
              <input value={form.notes || ""}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                placeholder="메모 입력"
                className="mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => { setShowForm(false); setEditingTx(null); }}
              className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
            <button type="submit" disabled={(editingTx ? updateMut.isPending : createMut.isPending) || !form.amount}
              className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
              {(editingTx ? updateMut.isPending : createMut.isPending) ? "저장 중..." : editingTx ? "수정" : "추가"}
            </button>
          </div>
        </form>
      )}

      {showForm && form.transaction_type === "DIVIDEND" && accountPositions.length > 0 && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 p-4">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">보유 종목 참고</p>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 dark:text-gray-500">
                <th className="text-left pb-1">종목코드</th>
                <th className="text-left pb-1">종목명</th>
                <th className="text-right pb-1">수량</th>
              </tr>
            </thead>
            <tbody>
              {accountPositions.map((p) => (
                <tr
                  key={p.ticker}
                  className="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-white dark:hover:bg-gray-700 transition-colors"
                  onClick={() => setForm((f) => ({ ...f, ticker: p.ticker }))}
                >
                  <td className="py-1.5 text-blue-600 dark:text-blue-400 font-medium">{p.ticker}</td>
                  <td className="py-1.5 text-gray-700 dark:text-gray-300">{p.name}</td>
                  <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">{p.qty.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

      <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-gray-400 dark:text-gray-500 text-sm">불러오는 중...</div>
        ) : filtered.length === 0 ? (
          <div className="py-12 text-center text-gray-400 dark:text-gray-500 text-sm">등록된 내역이 없습니다.</div>
        ) : (
          <>
            {/* 모바일 카드 뷰 */}
            <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
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
                      <button onClick={() => startEdit(tx)}
                        className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
                        <Pencil size={14} />
                      </button>
                      <button onClick={() => deleteMut.mutate(tx.id)} disabled={deleteMut.isPending}
                        className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors">
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                  {tx.notes && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{tx.notes}</p>
                  )}
                </div>
              ))}
            </div>

            {/* 데스크탑 테이블 */}
            <table className="hidden sm:table w-full text-sm">
              <thead>
                <tr className="bg-gray-50 dark:bg-gray-800 border-b border-gray-100 dark:border-gray-700">
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">날짜</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">구분</th>
                  <th className="text-right px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">금액</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">계좌</th>
                  <th className="text-left px-3 py-3 text-xs font-medium text-gray-400 dark:text-gray-500 uppercase">메모</th>
                  <th className="px-3 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((tx: Transaction) => (
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
                        <button onClick={() => startEdit(tx)}
                          className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
                          <Pencil size={15} />
                        </button>
                        <button onClick={() => deleteMut.mutate(tx.id)} disabled={deleteMut.isPending}
                          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors">
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
