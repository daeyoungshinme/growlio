import { useState } from "react";
import { useForm } from "@/hooks/useForm";
import { useStockSearch } from "@/hooks/useStockSearch";
import { useUsdAmountInput } from "@/hooks/useUsdAmountInput";
import type { Transaction, TransactionCreate } from "@/api/transactions";
import { localToday } from "@/utils/format";
import { TX_TYPES, type TxType } from "@/constants/transaction";

const isValidTxType = (val: unknown): val is TxType => TX_TYPES.includes(val as TxType);

const makeEmptyForm = (accountId: string): TransactionCreate => ({
  account_id: accountId,
  transaction_type: "DEPOSIT",
  amount: 0,
  transaction_date: localToday(),
  ticker: "",
  notes: "",
});

export function useTransactionFormState(accountId: string) {
  const { form, set, setForm } = useForm<TransactionCreate>(makeEmptyForm(accountId));
  const [formError, setFormError] = useState<string | null>(null);
  const [tickerDirect, setTickerDirect] = useState(false);
  const [tickerQuery, setTickerQuery] = useState("");
  const [showTickerSuggestions, setShowTickerSuggestions] = useState(false);
  const [editingTx, setEditingTx] = useState<Transaction | null>(null);
  const [depositPrompt, setDepositPrompt] = useState<{
    amount: number;
    txType: TxType;
  } | null>(null);

  const usd = useUsdAmountInput(form.amount, (krw) => set("amount", krw));
  const {
    suggestions: tickerSuggestions,
    isSearching: tickerSearchLoading,
    search: runTickerSearch,
    clearSuggestions: clearTickerSuggestions,
  } = useStockSearch();

  const resetForm = () => {
    setForm(makeEmptyForm(accountId));
    setFormError(null);
    usd.reset();
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
    usd.reset();
    clearTickerSuggestions();
    setShowTickerSuggestions(false);
  };

  const triggerDepositPrompt = (amt: number, txType: string) => {
    if (amt > 0 && isValidTxType(txType)) {
      setDepositPrompt({ amount: amt, txType });
    }
  };

  const handleTxTypeChange = (t: TxType) => {
    set("transaction_type", t);
    usd.reset();
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
    currency: usd.currency,
    amountUsd: usd.amountUsd,
    usdRate: usd.usdRate,
    usdConversionError: usd.conversionError,
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
    handleCurrencySwitch: usd.switchCurrency,
    handleUsdAmountChange: usd.changeUsd,
    handleTxTypeChange,
    handleTickerQueryChange,
  };
}
