import { useEffect, useRef, useState } from "react";
import { searchStocks, type StockSuggestion } from "../api/assets";

export function useStockSearch(debounceMs = 300) {
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, []);

  const search = (query: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!query.trim()) {
      setSuggestions([]);
      return;
    }
    timerRef.current = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsSearching(true);
      try {
        setSuggestions(await searchStocks(query.trim(), controller.signal));
      } catch {
        setSuggestions([]);
      } finally {
        setIsSearching(false);
      }
    }, debounceMs);
  };

  const clearSuggestions = () => setSuggestions([]);

  return { suggestions, isSearching, search, clearSuggestions };
}
