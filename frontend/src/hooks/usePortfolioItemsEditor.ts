import { useEffect, useRef, useState } from "react";
import type { StockSuggestion } from "@/api/assets";
import type { PortfolioItem } from "@/api/portfolios";
import type { PortfolioOverview } from "@/types";
import { CASH_TICKER, KR_PROPERTY_MARKET, REAL_ESTATE_ASSET_TYPE } from "@/constants/assets";
import { PORTFOLIO_WEIGHT_TOLERANCE } from "@/constants/validation";
import { FOCUS_SETTLE_DELAY } from "@/constants/timers";
import { useStockSearch } from "./useStockSearch";
import { toast } from "@/utils/toast";

const EMPTY_ITEM: PortfolioItem = { ticker: "", name: "", market: "KOSPI", weight: 0 };

export function usePortfolioItemsEditor(initialItems: PortfolioItem[]) {
  const [items, setItems] = useState<PortfolioItem[]>(
    initialItems.length ? initialItems : [{ ...EMPTY_ITEM }],
  );
  const { suggestions, search: runStockSearch, clearSuggestions } = useStockSearch();
  const [activeRow, setActiveRow] = useState<number | null>(null);
  const [editingRows, setEditingRows] = useState<Set<number>>(new Set());
  const searchInputRefs = useRef<Map<number, HTMLInputElement>>(new Map());

  const totalWeight = items.reduce((s, i) => s + (Number(i.weight) || 0), 0);
  const weightOk = Math.abs(totalWeight - 100) < PORTFOLIO_WEIGHT_TOLERANCE;

  function addItem() {
    setItems((prev) => [...prev, { ...EMPTY_ITEM }]);
  }

  function updateItem(idx: number, patch: Partial<PortfolioItem>) {
    setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }

  function addCash() {
    if (items.some((i) => i.ticker === CASH_TICKER)) return;
    setItems((prev) => [...prev, { ticker: CASH_TICKER, name: "현금", market: "KRW", weight: 0 }]);
  }

  function addRealEstate() {
    if (items.some((i) => i.market === KR_PROPERTY_MARKET)) return;
    setItems((prev) => [
      ...prev,
      { ticker: REAL_ESTATE_ASSET_TYPE, name: "부동산", market: KR_PROPERTY_MARKET, weight: 0 },
    ]);
  }

  function fillFromHoldings(overview: PortfolioOverview | undefined) {
    const hasData = items.some((i) => i.ticker && i.name);
    if (hasData && !confirm("입력된 종목을 현재 보유 비중으로 교체하시겠습니까?")) return;

    if (!overview?.all_positions.length) {
      toast("보유 종목 데이터가 없습니다. 계좌 동기화 후 다시 시도해주세요.", "error");
      return;
    }

    const grouped = new Map<
      string,
      { ticker: string; name: string; market: string; totalValue: number }
    >();
    for (const p of overview.all_positions) {
      if (!p.ticker || p.value_krw <= 0) continue;
      const key = `${p.ticker}-${p.market}`;
      const existing = grouped.get(key);
      if (existing) existing.totalValue += p.value_krw;
      else
        grouped.set(key, {
          ticker: p.ticker,
          name: p.name,
          market: p.market,
          totalValue: p.value_krw,
        });
    }

    const entries = [...grouped.values()].sort((a, b) => b.totalValue - a.totalValue);
    if (!entries.length) {
      toast("보유 종목이 없습니다.", "error");
      return;
    }

    const totalValue = entries.reduce((s, e) => s + e.totalValue, 0);
    const newItems: PortfolioItem[] = entries.map((e) => ({
      ticker: e.ticker,
      name: e.name,
      market: e.market,
      weight: Math.round((e.totalValue / totalValue) * 1000) / 10,
    }));
    // 반올림 오차 보정: 마지막 항목에 나머지 비중 합산
    const diff = Math.round((100 - newItems.reduce((s, i) => s + i.weight, 0)) * 10) / 10;
    if (newItems.length > 0 && diff !== 0) newItems[newItems.length - 1].weight += diff;

    setItems(newItems);
  }

  function handleTickerInput(idx: number, value: string) {
    updateItem(idx, { ticker: value });
    if (value.length < 1) {
      clearSuggestions();
      return;
    }
    setActiveRow(idx);
    runStockSearch(value);
  }

  function selectSuggestion(idx: number, s: StockSuggestion) {
    updateItem(idx, { ticker: s.ticker, name: s.name, market: s.market });
    clearSuggestions();
    setActiveRow(null);
    setEditingRows((prev) => {
      const next = new Set(prev);
      next.delete(idx);
      return next;
    });
  }

  function startEditing(idx: number) {
    updateItem(idx, { ticker: "", name: "" });
    setEditingRows((prev) => new Set(prev).add(idx));
    clearSuggestions();
    setTimeout(() => searchInputRefs.current.get(idx)?.focus(), FOCUS_SETTLE_DELAY);
  }

  function registerInputRef(idx: number, el: HTMLInputElement | null) {
    if (el) searchInputRefs.current.set(idx, el);
    else searchInputRefs.current.delete(idx);
  }

  useEffect(() => {
    const handler = () => {
      clearSuggestions();
      setActiveRow(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [clearSuggestions]);

  return {
    items,
    setItems,
    totalWeight,
    weightOk,
    suggestions,
    activeRow,
    setActiveRow,
    editingRows,
    addItem,
    updateItem,
    removeItem,
    addCash,
    addRealEstate,
    fillFromHoldings,
    handleTickerInput,
    selectSuggestion,
    startEditing,
    registerInputRef,
  };
}
