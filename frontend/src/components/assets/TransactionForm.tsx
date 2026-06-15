import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { AssetAccount } from "@/api/assets";
import {
  createTransaction,
  updateTransaction,
  type Transaction,
  type TransactionCreate,
} from "@/api/transactions";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { useForm } from "@/hooks/useForm";
import { useStockSearch } from "@/hooks/useStockSearch";
import { invalidateTransactionData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { TX_LABELS } from "@/constants/transaction";
import { STALE_TIME } from "@/constants/queryConfig";
import { INPUT_MD, LABEL_MD } from "@/constants/inputStyles";
import { SEARCH_DROPDOWN_HIDE_DELAY } from "@/constants/timers";
import { extractErrorMessage } from "@/utils/error";

const today = new Date().toISOString().slice(0, 10);

const EMPTY_FORM: TransactionCreate = {
  account_id: "",
  transaction_type: "DEPOSIT",
  amount: 0,
  fee: undefined,
  transaction_date: today,
  ticker: "",
  notes: "",
};

interface Props {
  accounts: AssetAccount[];
  editingTx: Transaction | null;
  onSuccess: (accId: string, amount: number, txType: string) => void;
  onCancel: () => void;
}

export function TransactionForm({ accounts, editingTx, onSuccess, onCancel }: Props) {
  const qc = useQueryClient();
  const usdRate = useExchangeRate();

  const initial: TransactionCreate = editingTx
    ? {
        account_id: editingTx.account_id ?? "",
        transaction_type: editingTx.transaction_type,
        amount: editingTx.amount,
        fee: editingTx.fee ?? undefined,
        transaction_date: editingTx.transaction_date,
        ticker: editingTx.ticker ?? "",
        notes: editingTx.notes ?? "",
      }
    : EMPTY_FORM;

  const { form, set: setField } = useForm<TransactionCreate>(initial);
  const [currency, setCurrency] = useState<"KRW" | "USD">("KRW");
  const [amountUsd, setAmountUsd] = useState(0);
  const [tickerDirect, setTickerDirect] = useState(!!editingTx?.ticker);
  const [tickerQuery, setTickerQuery] = useState(editingTx?.ticker ?? "");
  const {
    suggestions: tickerSuggestions,
    isSearching: tickerSearchLoading,
    search: runTickerSearch,
    clearSuggestions: clearTickerSuggestions,
  } = useStockSearch();
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);

  const { data: positionsData } = useQuery<{
    positions: Array<{ ticker: string; name: string; qty: number }>;
  }>({
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

  const resetTicker = () => {
    setTickerDirect(false);
    setTickerQuery("");
    clearTickerSuggestions();
    setShowTickerSuggestions(false);
  };

  const createMut = useMutation({
    mutationFn: createTransaction,
    onSuccess: (_, vars) => {
      invalidateTransactionData(qc);
      toast("추가되었습니다", "success");
      onSuccess(vars.account_id as string ?? "", vars.amount ?? 0, vars.transaction_type);
    },
    onError: (e) => toast(extractErrorMessage(e, "내역 저장에 실패했습니다"), "error"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TransactionCreate> }) =>
      updateTransaction(id, data),
    onSuccess: (_, vars) => {
      invalidateTransactionData(qc);
      toast("수정되었습니다", "success");
      onSuccess(vars.data?.account_id as string ?? "", vars.data?.amount ?? 0, vars.data?.transaction_type ?? "");
    },
    onError: (e) => toast(extractErrorMessage(e, "내역 수정에 실패했습니다"), "error"),
  });

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

  const isPending = editingTx ? updateMut.isPending : createMut.isPending;
  const inputCls = `mt-1 w-full ${INPUT_MD}`;
  const labelCls = LABEL_MD;

  return (
    <>
      <form
        onSubmit={handleSubmit}
        className={`bg-white dark:bg-gray-900 rounded-2xl border p-5 space-y-4 ${editingTx ? "border-amber-200 dark:border-amber-800" : "border-blue-200 dark:border-blue-800"}`}
      >
        <div className="flex gap-2">
          {(["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const).map((t) => (
            <button key={t} type="button"
              onClick={() => { setField("transaction_type", t); setCurrency("KRW"); setAmountUsd(0); resetTicker(); }}
              className={`flex-1 py-3 text-sm font-medium rounded-lg border transition-colors ${
                form.transaction_type === t
                  ? "bg-blue-600 text-white border-blue-600"
                  : "border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-300 dark:hover:border-blue-600"
              }`}>
              {TX_LABELS[t]}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="txform-account" className={labelCls}>계좌 선택</label>
            <select id="txform-account" value={form.account_id}
              onChange={(e) => { setField("account_id", e.target.value); setField("ticker", ""); resetTicker(); }}
              className={inputCls}>
              <option value="">계좌 미지정</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="txform-date" className={labelCls}>날짜 *</label>
            <input id="txform-date" type="date" required value={form.transaction_date}
              onChange={(e) => setField("transaction_date", e.target.value)}
              className={inputCls} />
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <div className="flex items-center justify-between">
              <label className={labelCls}>금액 *</label>
              {form.transaction_type === "DIVIDEND" && (
                <div className="flex gap-0.5 text-xs">
                  {(["KRW", "USD"] as const).map((c) => (
                    <button key={c} type="button"
                      onClick={() => { setCurrency(c); setAmountUsd(0); }}
                      className={`px-2.5 py-1.5 rounded transition-colors ${currency === c ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-600"}`}>
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
                  <input type="number" inputMode="decimal"
                    value={amountUsd || ""}
                    onChange={(e) => {
                      const usd = parseFloat(e.target.value) || 0;
                      setAmountUsd(usd);
                      if (usdRate) setField("amount", Math.round(usd * usdRate));
                    }}
                    placeholder="0.00" step="0.01" min={0} className={inputCls} />
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
              <input type="number" inputMode="decimal" required min={1} value={form.amount || ""}
                onChange={(e) => setField("amount", Number(e.target.value))}
                placeholder="예: 500000" className={`${inputCls} mt-1`} />
            )}
          </div>
          {form.transaction_type === "DIVIDEND" ? (
            <div>
              <label className={labelCls}>종목 (선택)</label>
              {accountPositions.length > 0 && !tickerDirect ? (
                <select value={form.ticker || ""}
                  onChange={(e) => {
                    if (e.target.value === "__direct__") { setTickerDirect(true); setField("ticker", ""); }
                    else { setField("ticker", e.target.value); }
                  }}
                  className={inputCls}>
                  <option value="">종목 선택</option>
                  {accountPositions.map((p) => <option key={p.ticker} value={p.ticker}>{p.name}</option>)}
                  <option value="__direct__">기타 종목 직접 입력...</option>
                </select>
              ) : (
                <div className="flex gap-1 mt-1">
                  <div className="relative w-full">
                    <input
                      value={tickerQuery}
                      onChange={(e) => {
                        const v = e.target.value;
                        setTickerQuery(v); setField("ticker", v);
                        setShowTickerSuggestions(true);
                        if (!v.trim()) { clearTickerSuggestions(); return; }
                        runTickerSearch(v);
                      }}
                      onFocus={() => tickerSuggestions.length > 0 && setShowTickerSuggestions(true)}
                      onBlur={() => setTimeout(() => setShowTickerSuggestions(false), SEARCH_DROPDOWN_HIDE_DELAY)}
                      placeholder="종목명 또는 코드 검색"
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    {tickerSearchLoading && (
                      <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">검색 중...</span>
                    )}
                    {showTickerSuggestions && tickerSuggestions.length > 0 && (
                      <ul
                        role="listbox"
                        aria-label="종목 검색 결과"
                        className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-48 overflow-y-auto"
                      >
                        {tickerSuggestions.map((s) => (
                          <li
                            key={s.ticker}
                            role="option"
                            aria-selected={false}
                            tabIndex={0}
                            className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2 focus:bg-blue-50 dark:focus:bg-blue-950 focus:outline-none"
                            onMouseDown={() => { setTickerQuery(s.name); setField("ticker", s.ticker); clearTickerSuggestions(); setShowTickerSuggestions(false); }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                setTickerQuery(s.name); setField("ticker", s.ticker); clearTickerSuggestions(); setShowTickerSuggestions(false);
                              }
                            }}
                          >
                            <span className="font-medium text-blue-700 dark:text-blue-400">{s.ticker}</span>
                            <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
                            <span className="text-xs text-gray-400 ml-auto">{s.market}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {accountPositions.length > 0 && (
                    <button type="button"
                      onClick={() => { setTickerDirect(false); setField("ticker", ""); setTickerQuery(""); clearTickerSuggestions(); setShowTickerSuggestions(false); }}
                      className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap">
                      ← 목록
                    </button>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div>
              <label className={labelCls}>메모 (선택)</label>
              <input value={form.notes || ""} onChange={(e) => setField("notes", e.target.value)}
                placeholder="메모 입력" className={`${inputCls} mt-1`} />
            </div>
          )}
        </div>
        {form.transaction_type === "DIVIDEND" && (
          <div>
            <label htmlFor="txform-notes" className={labelCls}>메모 (선택)</label>
            <input id="txform-notes" value={form.notes || ""} onChange={(e) => setField("notes", e.target.value)}
              placeholder="메모 입력" className={`${inputCls} mt-1`} />
          </div>
        )}
        <div>
          <label htmlFor="txform-fee" className={labelCls}>거래 수수료 (선택)</label>
          <input
            id="txform-fee"
            type="number"
            inputMode="numeric"
            min={0}
            step={1}
            value={form.fee ?? ""}
            onChange={(e) => setField("fee", e.target.value ? Number(e.target.value) : undefined)}
            placeholder="예: 350"
            className={`${inputCls} mt-1`}
          />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel}
            className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors">취소</button>
          <button type="submit" disabled={isPending || !form.amount} aria-busy={isPending}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {isPending ? "저장 중..." : editingTx ? "수정" : "추가"}
          </button>
        </div>
      </form>

      {form.transaction_type === "DIVIDEND" && accountPositions.length > 0 && (
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
                <tr key={p.ticker}
                  className="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-white dark:hover:bg-gray-700 transition-colors"
                  onClick={() => setField("ticker", p.ticker)}>
                  <td className="py-1.5 text-blue-600 dark:text-blue-400 font-medium">{p.ticker}</td>
                  <td className="py-1.5 text-gray-700 dark:text-gray-300">{p.name}</td>
                  <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">{p.qty.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
