import { useState } from "react";
import { fetchStockPrice } from "../api/assets";
import type { StockSuggestion } from "../api/assets";
import { useStockSearch } from "./useStockSearch";
import { extractErrorMessage } from "../utils/error";
import { toast } from "../utils/toast";
import { isOverseasMarket } from "../constants/markets";

export interface Position {
  ticker: string;
  name: string;
  market: string;
  qty: number;
  avg_price: number;
  avg_price_usd: number | null;
  usd_rate: number | null;
  current_price: number | null;
  current_price_usd?: number | null;
  invested_amount?: number;
  value_amount?: number;
  pnl?: number;
  pnl_pct?: number;
}

export function usePositionsEditor(initialRows: Position[], usdRate: number | null) {
  const [rows, setRows] = useState<Position[]>(initialRows);
  const [suggestIdx, setSuggestIdx] = useState<number | null>(null);
  const [priceLoadingRows, setPriceLoadingRows] = useState<Set<number>>(new Set());

  const { suggestions, isSearching: searchLoading, search: runStockSearch, clearSuggestions } = useStockSearch();

  const setRow = (i: number, patch: Partial<Position>) =>
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));

  const addRow = () =>
    setRows((prev) => [
      ...prev,
      { ticker: "", name: "", market: "KOSPI", qty: 0, avg_price: 0, avg_price_usd: null, usd_rate: null, current_price: null, current_price_usd: null },
    ]);

  const removeRow = (i: number) => {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
    if (suggestIdx === i) { clearSuggestions(); setSuggestIdx(null); }
  };

  const loadPrice = async (i: number, ticker: string, market: string) => {
    if (!ticker) return;
    setPriceLoadingRows((prev) => new Set([...prev, i]));
    try {
      const result = await fetchStockPrice(ticker, market);
      if (result.price_krw) {
        setRow(i, {
          current_price: result.price_krw,
          current_price_usd: result.price_usd ?? null,
          ...(result.usd_rate ? { usd_rate: result.usd_rate } : {}),
        });
      }
    } catch (e: unknown) {
      toast(extractErrorMessage(e, "현재가 조회에 실패했습니다"));
    } finally {
      setPriceLoadingRows((prev) => { const s = new Set(prev); s.delete(i); return s; });
    }
  };

  const handleNameChange = (i: number, value: string) => {
    setRow(i, { name: value });
    if (!value.trim()) { clearSuggestions(); setSuggestIdx(null); return; }
    setSuggestIdx(i);
    runStockSearch(value);
  };

  const handleNameBlur = (i: number) => {
    setTimeout(() => { if (suggestIdx === i) { clearSuggestions(); setSuggestIdx(null); } }, 150);
  };

  const handleSelectSuggestion = (i: number, s: StockSuggestion) => {
    setRows((prev) =>
      prev.map((r, idx) =>
        idx === i ? { ...r, ticker: s.ticker, name: s.name, market: s.market } : r
      )
    );
    clearSuggestions();
    setSuggestIdx(null);
    void loadPrice(i, s.ticker, s.market);
  };

  const handleAvgPriceUsd = (i: number, usdVal: string) => {
    const usd = usdVal === "" ? 0 : parseFloat(usdVal) || 0;
    const krw = usdRate ? Math.floor(usd * usdRate) : 0;
    setRow(i, { avg_price_usd: usd || null, usd_rate: usdRate, avg_price: krw });
  };

  const handleCurrentPriceUsd = (i: number, usdVal: string) => {
    const usd = usdVal === "" ? null : parseFloat(usdVal) || null;
    const krw = usd && usdRate ? Math.round(usd * usdRate) : null;
    setRow(i, { current_price_usd: usd, current_price: krw });
  };

  const liveRows = rows.map((r) => {
    const cur = r.current_price ?? r.avg_price;
    const invested = r.qty * r.avg_price;
    const value = r.qty * cur;
    const pnl = value - invested;
    const pnl_pct = invested ? (pnl / invested) * 100 : 0;
    return { ...r, current_price: cur, invested_amount: invested, value_amount: value, pnl, pnl_pct };
  });

  const enrichRows = (positions: Position[]): Position[] =>
    positions.map((p) => ({
      ...p,
      current_price_usd:
        isOverseasMarket(p.market) && p.current_price && p.usd_rate
          ? +(p.current_price / p.usd_rate).toFixed(4)
          : (p.current_price_usd ?? null),
    }));

  return {
    rows,
    liveRows,
    setRows,
    enrichRows,
    suggestIdx,
    setSuggestIdx,
    priceLoadingRows,
    suggestions,
    searchLoading,
    setRow,
    addRow,
    removeRow,
    handleNameChange,
    handleNameBlur,
    handleSelectSuggestion,
    handleAvgPriceUsd,
    handleCurrentPriceUsd,
  };
}
