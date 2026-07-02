import type { StockSuggestion } from "@/api/assets";
import type { TransactionCreate } from "@/api/transactions";
import { SEARCH_DROPDOWN_HIDE_DELAY } from "@/constants/timers";
import { useForm } from "@/hooks/useForm";

interface AccountPosition {
  ticker: string;
  name: string;
  qty: number;
}

interface Props {
  set: ReturnType<typeof useForm<TransactionCreate>>["set"];
  ticker: string;
  accountPositions: AccountPosition[];
  tickerDirect: boolean;
  setTickerDirect: (v: boolean) => void;
  tickerQuery: string;
  tickerSuggestions: StockSuggestion[];
  tickerSearchLoading: boolean;
  showTickerSuggestions: boolean;
  setShowTickerSuggestions: (v: boolean) => void;
  clearTickerSuggestions: () => void;
  onTickerQueryChange: (v: string) => void;
}

// 배당 거래 전용 종목 선택 — 보유종목 드롭다운 또는 직접 검색
export default function TransactionTickerField({
  set,
  ticker,
  accountPositions,
  tickerDirect,
  setTickerDirect,
  tickerQuery,
  tickerSuggestions,
  tickerSearchLoading,
  showTickerSuggestions,
  setShowTickerSuggestions,
  clearTickerSuggestions,
  onTickerQueryChange,
}: Props) {
  return (
    <>
      <div>
        <label className="text-xs font-medium text-gray-600 dark:text-gray-400">종목 (선택)</label>
        {accountPositions.length > 0 && !tickerDirect ? (
          <select
            className="mt-1 w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={ticker || ""}
            onChange={(e) => {
              if (e.target.value === "__direct__") {
                setTickerDirect(true);
                set("ticker", "");
              } else {
                set("ticker", e.target.value);
              }
            }}
          >
            <option value="">종목 선택</option>
            {accountPositions.map((p) => (
              <option key={p.ticker} value={p.name}>
                {p.name}
              </option>
            ))}
            <option value="__direct__">기타 종목 직접 입력...</option>
          </select>
        ) : (
          <div className="flex gap-1 mt-1">
            <div className="relative w-full">
              <input
                value={tickerQuery}
                onChange={(e) => onTickerQueryChange(e.target.value)}
                onFocus={() => tickerSuggestions.length > 0 && setShowTickerSuggestions(true)}
                onBlur={() => setTimeout(() => setShowTickerSuggestions(false), SEARCH_DROPDOWN_HIDE_DELAY)}
                placeholder="종목명 또는 코드 검색"
                className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {tickerSearchLoading && (
                <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                  검색 중...
                </span>
              )}
              {showTickerSuggestions && tickerSuggestions.length > 0 && (
                <ul className="absolute z-20 left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-0.5 max-h-40 overflow-y-auto">
                  {tickerSuggestions.map((s) => (
                    <li
                      key={s.ticker}
                      className="px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-950 cursor-pointer text-sm flex items-center gap-2"
                      onMouseDown={() => {
                        onTickerQueryChange(s.name);
                        set("ticker", s.name);
                        clearTickerSuggestions();
                        setShowTickerSuggestions(false);
                      }}
                    >
                      <span className="font-medium text-blue-700 dark:text-blue-400">{s.ticker}</span>
                      <span className="text-gray-700 dark:text-gray-300">{s.name}</span>
                      <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto">{s.market}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {accountPositions.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  setTickerDirect(false);
                  set("ticker", "");
                  onTickerQueryChange("");
                }}
                className="shrink-0 px-2 text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap"
              >
                ← 목록
              </button>
            )}
          </div>
        )}
      </div>

      {/* 보유 종목 참고 */}
      {accountPositions.length > 0 && (
        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">보유 종목 참고</p>
          <div className="max-h-28 overflow-y-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-400 dark:text-gray-500">
                  <th className="text-left pb-1">종목명</th>
                  <th className="text-right pb-1">수량</th>
                </tr>
              </thead>
              <tbody>
                {accountPositions.map((p) => (
                  <tr
                    key={p.ticker}
                    className="border-t border-gray-100 dark:border-gray-700 cursor-pointer hover:bg-white dark:hover:bg-gray-700 transition-colors"
                    onClick={() => {
                      set("ticker", p.name);
                      setTickerDirect(false);
                      onTickerQueryChange("");
                    }}
                  >
                    <td className="py-1 text-gray-700 dark:text-gray-300">{p.name}</td>
                    <td className="py-1 text-right text-gray-500 dark:text-gray-400">
                      {p.qty?.toLocaleString() ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
