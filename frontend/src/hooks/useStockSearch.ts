import { useEffect, useRef, useState } from "react";
import { searchStocks, type StockSuggestion } from "../api/assets";
import { toast } from "../utils/toast";

export function useStockSearch(debounceMs = 300) {
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [isSearchError, setIsSearchError] = useState(false);
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
      setIsSearchError(false);
      return;
    }
    timerRef.current = setTimeout(async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setIsSearching(true);
      setIsSearchError(false);
      try {
        setSuggestions(await searchStocks(query.trim(), controller.signal));
      } catch {
        setSuggestions([]);
        if (!controller.signal.aborted) {
          setIsSearchError(true);
          toast("종목 검색에 실패했습니다", "error");
        }
      } finally {
        setIsSearching(false);
      }
    }, debounceMs);
  };

  const clearSuggestions = () => {
    setSuggestions([]);
    setIsSearchError(false);
  };

  return { suggestions, isSearching, isSearchError, search, clearSuggestions };
}
