import { Trash2 } from "lucide-react";
import type { StockSuggestion } from "@/api/assets";
import type { PortfolioItem } from "@/api/portfolios";
import { CASH_TICKER, KR_PROPERTY_MARKET } from "@/constants/assets";

interface Props {
  item: PortfolioItem;
  idx: number;
  isEditing: boolean;
  isActive: boolean;
  suggestions: StockSuggestion[];
  onRegisterInputRef: (idx: number, el: HTMLInputElement | null) => void;
  onTickerInput: (idx: number, value: string) => void;
  onFocus: (idx: number) => void;
  onSelectSuggestion: (idx: number, s: StockSuggestion) => void;
  onStartEditing: (idx: number) => void;
  onUpdateWeight: (idx: number, weight: number) => void;
  onRemove: (idx: number) => void;
}

// 포트폴리오 종목 한 행 — 현금/부동산/선택완료 표시/검색 4가지 모드
export default function PortfolioItemRow({
  item,
  idx,
  isEditing,
  isActive,
  suggestions,
  onRegisterInputRef,
  onTickerInput,
  onFocus,
  onSelectSuggestion,
  onStartEditing,
  onUpdateWeight,
  onRemove,
}: Props) {
  return (
    <div className="relative flex items-center gap-2">
      {item.ticker === CASH_TICKER ? (
        <div className="flex-1 flex items-center gap-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400 bg-gray-200 dark:bg-gray-700 px-2 py-0.5 rounded">
            현금
          </span>
          <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">KRW 현금</span>
        </div>
      ) : item.market === KR_PROPERTY_MARKET ? (
        <div className="flex-1 flex items-center gap-2 border border-amber-200 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/20 rounded-lg px-3 py-2">
          <span className="text-xs font-medium text-amber-700 bg-amber-200 px-2 py-0.5 rounded">
            부동산
          </span>
          <span className="text-sm text-gray-700 dark:text-gray-300 flex-1">
            REAL_ESTATE (순자산 합산)
          </span>
        </div>
      ) : item.ticker && item.name && !isEditing ? (
        /* 표시 모드: 종목 선택 완료 */
        <div className="flex-1 flex items-center justify-between gap-2 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-lg px-3 py-2">
          <div className="flex items-baseline gap-2 min-w-0">
            <span className="text-sm font-semibold text-gray-800 dark:text-gray-50 truncate">
              {item.name}
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
              {item.ticker} · {item.market}
            </span>
          </div>
          <button
            type="button"
            onClick={() => onStartEditing(idx)}
            className="text-xs text-blue-500 hover:text-blue-700 whitespace-nowrap flex-shrink-0"
          >
            변경
          </button>
        </div>
      ) : (
        /* 검색 모드: 종목 입력/검색 */
        <div className="flex-1 relative">
          <input
            ref={(el) => onRegisterInputRef(idx, el)}
            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 placeholder-gray-400 dark:placeholder-gray-500 rounded-lg px-3 py-2.5 sm:py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="종목명 또는 티커 검색 (예: 삼성전자, AAPL)"
            value={item.ticker}
            onChange={(e) => onTickerInput(idx, e.target.value)}
            onFocus={() => onFocus(idx)}
          />
          {isActive && suggestions.length > 0 && (
            <div
              className="absolute z-10 top-full left-0 right-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto"
              onMouseDown={(e) => e.stopPropagation()}
            >
              {suggestions.map((s) => (
                <button
                  key={`${s.ticker}-${s.market}`}
                  className="w-full text-left px-3 py-2 hover:bg-blue-50 dark:hover:bg-blue-900/30 flex items-center gap-2 text-sm"
                  onMouseDown={() => onSelectSuggestion(idx, s)}
                >
                  <span className="font-medium text-gray-800 dark:text-gray-50 flex-1 truncate">
                    {s.name}
                  </span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">{s.ticker}</span>
                  <span className="text-xs text-gray-400 dark:text-gray-500 ml-1">{s.market}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <input
        type="number"
        min={0}
        max={100}
        step={0.1}
        className="w-20 sm:w-24 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2.5 sm:py-2 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="%"
        value={item.weight || ""}
        onChange={(e) => onUpdateWeight(idx, parseFloat(e.target.value) || 0)}
      />
      <button
        onClick={() => onRemove(idx)}
        aria-label="항목 삭제"
        className="min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center p-1.5 text-gray-400 dark:text-gray-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg transition-colors"
      >
        <Trash2 size={15} />
      </button>
    </div>
  );
}
