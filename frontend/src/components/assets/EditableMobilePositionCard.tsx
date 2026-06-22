import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { convertUsdToKrw, fmtKrwShort } from "@/utils/format";
import { isOverseasMarket, POSITION_MARKETS } from "@/constants/markets";
import { SCROLL_INTO_VIEW_DELAY } from "@/constants/timers";
import { SuggestionDropdown } from "@/components/common/SuggestionDropdown";
import { PnlCell } from "./PositionHelpers";
import type { EditablePositionRowProps } from "./PositionHelpers";

export function EditableMobilePositionCard({
  row,
  rawRow,
  index: i,
  usdRate,
  priceLoading,
  suggestions,
  suggestIdx,
  searchLoading,
  setSuggestIdx,
  handleNameChange,
  handleNameBlur,
  handleSelectSuggestion,
  setRow,
  removeRow,
  handleAvgPriceUsd,
  handleCurrentPriceUsd,
  handleMarketChange,
}: EditablePositionRowProps) {
  const [activeInputEl, setActiveInputEl] = useState<HTMLInputElement | null>(null);
  const overseas = isOverseasMarket(row.market);

  return (
    <div className="py-3 space-y-2">
      <div className="relative">
        <input
          className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-base bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
          value={row.name}
          onChange={(e) => handleNameChange(i, e.target.value)}
          onFocus={(e) => {
            setActiveInputEl(e.currentTarget);
            if (row.name && suggestions.length) setSuggestIdx(i);
            const el = e.currentTarget;
            setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "nearest" }), SCROLL_INTO_VIEW_DELAY);
          }}
          onBlur={(e) => {
            setActiveInputEl(null);
            handleNameBlur(i);
            void e;
          }}
          placeholder="종목명 또는 코드 검색..."
          autoComplete="off"
        />
        {searchLoading && suggestIdx === i && (
          <span className="absolute right-3 top-2.5">
            <Loader2 size={14} className="animate-spin text-gray-400" />
          </span>
        )}
        {suggestIdx === i && suggestions.length > 0 && (
          <SuggestionDropdown
            rowIndex={i}
            suggestions={suggestions}
            anchorEl={activeInputEl}
            onSelect={handleSelectSuggestion}
          />
        )}
      </div>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {row.ticker && (
            <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full font-mono shrink-0">
              {row.ticker}
            </span>
          )}
          <select
            className="text-base border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg px-2 py-2 focus:outline-none"
            value={row.market}
            onChange={(e) => handleMarketChange(i, e.target.value, row.market)}
          >
            {POSITION_MARKETS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => removeRow(i)}
          aria-label={`${i + 1}번 행 삭제`}
          className="p-2 min-h-[44px] min-w-[44px] flex items-center justify-center text-gray-300 dark:text-gray-600 hover:text-red-500 rounded-lg"
        >
          <Trash2 size={16} />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">보유수량</p>
          <input
            type="number"
            inputMode="numeric"
            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
            value={row.qty || ""}
            onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
            min={0}
            placeholder="0"
          />
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">평단가</p>
          {overseas ? (
            <div>
              <div className="flex items-center gap-1">
                <span className="text-sm text-gray-400 shrink-0">$</span>
                <input
                  type="number"
                  inputMode="decimal"
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                  value={row.avg_price_usd ?? ""}
                  onChange={(e) => handleAvgPriceUsd(i, e.target.value)}
                  placeholder="0.00"
                  min={0}
                  step="0.01"
                />
              </div>
              {convertUsdToKrw(row.avg_price_usd, usdRate) > 0 && (
                <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                  ≈ ₩{convertUsdToKrw(row.avg_price_usd, usdRate).toLocaleString()}
                </div>
              )}
            </div>
          ) : (
            <input
              type="number"
              inputMode="decimal"
              className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
              value={row.avg_price || ""}
              onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
              min={0}
              placeholder="0"
            />
          )}
        </div>
      </div>
      <div>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">
          {overseas ? "현재가($)" : "현재가(원)"}
        </p>
        {overseas ? (
          <div className="relative">
            <span className="absolute left-3 top-2 text-sm text-gray-400 dark:text-gray-500 pointer-events-none">
              $
            </span>
            <input
              type="number"
              inputMode="decimal"
              className={`w-full border border-gray-300 dark:border-gray-600 rounded-lg pl-6 pr-3 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 transition-opacity ${priceLoading ? "opacity-50" : ""}`}
              value={rawRow.current_price_usd ?? ""}
              onChange={(e) => handleCurrentPriceUsd(i, e.target.value)}
              placeholder="자동조회"
              min={0}
              step="0.01"
              disabled={priceLoading}
            />
            {priceLoading && (
              <span className="absolute right-3 top-2.5">
                <Loader2 size={14} className="animate-spin text-blue-400" />
              </span>
            )}
            {convertUsdToKrw(rawRow.current_price_usd, usdRate) > 0 && (
              <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                ≈ ₩{convertUsdToKrw(rawRow.current_price_usd, usdRate).toLocaleString()}
              </div>
            )}
          </div>
        ) : (
          <div className="relative">
            <input
              type="number"
              inputMode="decimal"
              className={`w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 transition-opacity ${priceLoading ? "opacity-50" : ""}`}
              value={rawRow.current_price ?? ""}
              onChange={(e) =>
                setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })
              }
              placeholder="자동조회"
              min={0}
              disabled={priceLoading}
            />
            {priceLoading && (
              <span className="absolute right-3 top-2.5">
                <Loader2 size={14} className="animate-spin text-blue-400" />
              </span>
            )}
          </div>
        )}
      </div>
      <div className="border-t border-gray-100 dark:border-gray-800 pt-2 grid grid-cols-3 gap-x-3 pb-1">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">매입금액</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5 text-right">
            {fmtKrwShort(row.invested_amount ?? 0)}원
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5 text-right">
            {fmtKrwShort(row.value_amount ?? 0)}원
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">수익률</p>
          <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
        </div>
      </div>
    </div>
  );
}
