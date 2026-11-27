import { useCallback, useEffect, useRef, useState } from "react";
import { searchStocks, type StockSuggestion } from "@/api/assets";
import { toast } from "@/utils/toast";

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

  // 진행 중인 요청을 끊는다 — 끊지 않으면 검색창을 비운 뒤 도착한 응답이 옛 결과를 다시 띄운다(plans/116 C5)
  const cancelPending = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();
    abortRef.current = null;
    setIsSearching(false);
  }, []);

  const search = (query: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!query.trim()) {
      cancelPending();
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
        const result = await searchStocks(query.trim(), controller.signal);
        if (abortRef.current === controller) setSuggestions(result);
      } catch {
        // 새 검색에 밀려 중단된 요청은 상태를 건드리지 않는다 — 진행 중인 새 검색의 스피너·결과를 지운다
        if (controller.signal.aborted) return;
        setSuggestions([]);
        setIsSearchError(true);
        toast("종목 검색에 실패했습니다", "error");
      } finally {
        if (abortRef.current === controller) setIsSearching(false);
      }
    }, debounceMs);
  };

  // 안정 참조 — 호출부의 document 리스너 effect가 이것을 deps로 둔다. 렌더마다 새 함수면 키 입력마다
  // 리스너를 떼고 다시 붙인다(plans/156 B6)
  const clearSuggestions = useCallback(() => {
    cancelPending();
    setSuggestions([]);
    setIsSearchError(false);
  }, [cancelPending]);

  return { suggestions, isSearching, isSearchError, search, clearSuggestions };
}
