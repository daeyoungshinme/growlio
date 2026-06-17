import { useState } from "react";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { useForm } from "@/hooks/useForm";
import { useStockSearch } from "@/hooks/useStockSearch";
import type { Transaction, TransactionCreate } from "@/api/transactions";
import { convertUsdToKrw } from "@/utils/format";

const VALID_TX_TYPES = ["DEPOSIT", "WITHDRAWAL", "DIVIDEND"] as const;
type TxType = (typeof VALID_TX_TYPES)[number];

const isValidTxType = (val: unknown): val is TxType => VALID_TX_TYPES.includes(val as TxType);

const makeEmptyForm = (accountId: string): TransactionCreate => ({
  account_id: accountId,
  transaction_type: "DEPOSIT",
  amount: 0,
  transaction_date: new Date().toISOString().slice(0, 10),
  ticker: "",
  notes: "",
});

export function useTransactionFormState(accountId: string) {
  const { form, set, setForm } = useForm<TransactionCreate>(makeEmptyForm(accountId));
  const [formError, setFormError] = useState<string | null>(null);
  const [currency, setCurrency] = useState<"KRW" | "USD">("KRW");
  const [amountUsd, setAmountUsd] = useState<number>(0);
  const [tickerDirect, setTickerDirect] = useState(false);
  const [tickerQuery, setTickerQuery] = useState("");
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [depositPrompt, setDepositPrompt] = useState<{
    amount: number;
    txType: TxType;
  } | null>(null);

  const usdRate = useExchangeRate();
  const {
    suggestions: tickerSuggestions,
    isSearching: tickerSearchLoading,
    search: runTickerSearch,
    clearSuggestions: clearTickerSuggestions,
  } = useStockSearch();

  const resetForm = () => {
    setForm(makeEmptyForm(accountId));
    setFormError(null);
    setCurrency("KRW");
    setAmountUsd(0);
    setTickerDirect(false);
    setTickerQuery("");
    clearTickerSuggestions();
    setShowTickerSuggestions(false);
  };

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
    setCurrency("KRW");
    setAmountUsd(0);
    clearTickerSuggestions();
    setShowTickerSuggestions(false);
  };

  const triggerDepositPrompt = (amt: number, txType: string) => {
    if (amt > 0 && isValidTxType(txType)) {
      setDepositPrompt({ amount: amt, txType });
    }
  };

  const handleCurrencySwitch = (c: "KRW" | "USD") => {
    if (c === currency) return;
    if (c === "USD") {
      setAmountUsd(usdRate && form.amount ? parseFloat((form.amount / usdRate).toFixed(2)) : 0);
    } else {
      setAmountUsd(0);
    }
    setCurrency(c);
  };

  const handleUsdAmountChange = (usd: number) => {
    setAmountUsd(usd);
    set("amount", convertUsdToKrw(usd, usdRate));
  };

  const handleTxTypeChange = (t: TxType) => {
    set("transaction_type", t);
    setCurrency("KRW");
    setAmountUsd(0);
    setTickerDirect(false);
    setTickerQuery("");
    clearTickerSuggestions();
    setShowTickerSuggestions(false);
  };

  const handleTickerQueryChange = (v: string) => {
    setTickerQuery(v);
    set("ticker", v);
    setShowTickerSuggestions(true);
    if (!v.trim()) {
      clearTickerSuggestions();
      return;
    }
    runTickerSearch(v);
  };

  return {
    form,
    set,
    setForm,
    formError,
    setFormError,
    currency,
    amountUsd,
    usdRate,
    tickerDirect,
    setTickerDirect,
    tickerQuery,
    setTickerQuery,
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
  };
}
