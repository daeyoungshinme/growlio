import { useState } from "react";
import { useStockSearch } from "@/hooks/useStockSearch";
import { SEARCH_DROPDOWN_HIDE_DELAY } from "@/constants/timers";
import { INPUT_MD, LABEL_MD } from "@/constants/inputStyles";

interface Position {
  ticker: string;
  name: string;
}

interface Props {
  accountPositions: Position[];
  ticker: string;
  initialQuery?: string;
  onTickerChange: (ticker: string) => void;
}

export function TickerSearchField({ accountPositions, ticker, initialQuery = "", onTickerChange }: Props) {
  const [directInput, setDirectInput] = useState(!accountPositions.length || !!initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const { suggestions, isSearching, search, clearSuggestions } = useStockSearch();

  const handleSelect = (name: string, code: string) => {
    setQuery(name);
    onTickerChange(code);
    clearSuggestions();
    setShowSuggestions(false);
  };

  const handleBackToList = () => {
    setDirectInput(false);
    setQuery("");
    onTickerChange("");
    clearSuggestions();
    setShowSuggestions(false);
  };

  return (
    <div>
      <label className={LABEL_MD}>종목 (선택)</label>
      {accountPositions.length > 0 && !directInput ? (
        <select
          value={ticker || ""}
          onChange={(e) => {
            if (e.target.value === "__direct__") {
              setDirectInput(true);
              onTickerChange("");
            } else {
              onTickerChange(e.target.value);
            }
          }}
          className={INPUT_MD}
        >
          <option value="">종목 선택</option>
          {accountPositions.map((p) => (
            <option key={p.ticker} value={p.ticker}>
              {p.name}
            </option>
          ))}
          <option value="__direct__">기타 종목 직접 입력...</option>
        </select>
      ) : (
        <div className="flex gap-1 mt-1">
          <div className="relative w-full">
            <input
              value={query}
              onChange={(e) => {
                const v = e.target.value;
                setQuery(v);
                onTickerChange(v);
                setShowSuggestions(true);
                if (!v.trim()) {
                  clearSuggestions();
                  return;
                }
                search(v);
              }}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              onBlur={() =>
                setTimeout(() => setShowSuggestions(false), SEARCH_DROPDOWN_HIDE_DELAY)
              }
              placeholder="종목명 또는 코드 검색"
              className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-base focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {isSearching && (
              <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                검색 중...
              </span>
            )}
            {showSuggestions && suggestions.length > 0 && (
              <ul
                role="listbox"
                aria-label="종목 검색 결과"
                className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-48 overflow-y-auto"
              >
                {suggestions.map((s) => (
                  <li
                    key={s.ticker}
                    role="option"
                    aria-selected={false}
                    tabIndex={0}
                    className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2 focus:bg-blue-50 dark:focus:bg-blue-950 focus:outline-none"
                    onMouseDown={() => handleSelect(s.name, s.ticker)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSelect(s.name, s.ticker);
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
            <button
              type="button"
              onClick={handleBackToList}
              className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap"
            >
              ← 목록
            </button>
          )}
        </div>
      )}
    </div>
  );
}
