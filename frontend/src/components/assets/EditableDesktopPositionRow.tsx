import { Loader2, Trash2 } from "lucide-react";
import { convertUsdToKrw, fmtKrwShort } from "@/utils/format";
import { isOverseasMarket } from "@/constants/markets";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { PnlCell, MarketSelect } from "./PositionHelpers";
import type { EditablePositionRowProps } from "./PositionHelpers";

export function EditableDesktopPositionRow({
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
  const overseas = isOverseasMarket(row.market);

  return (
    <tr className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 align-top">
      <td className="py-2 pr-3">
        <div className="relative">
          <input
            className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
            value={row.name}
            onChange={(e) => handleNameChange(i, e.target.value)}
            onFocus={() => {
              if (row.name && suggestions.length) setSuggestIdx(i);
            }}
            onBlur={() => handleNameBlur(i)}
            placeholder="종목명 또는 코드 검색..."
            autoComplete="off"
          />
          {(row.ticker || row.market !== "KOSPI") && (
            <div className="flex items-center gap-1 mt-0.5">
              {row.ticker && (
                <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">
                  {row.ticker}
                </span>
              )}
              {row.ticker && <span className="text-gray-300 dark:text-gray-600 text-xs">·</span>}
              <MarketSelect
                value={row.market}
                disabled={false}
                onChange={(m) => handleMarketChange(i, m, row.market)}
              />
            </div>
          )}
          {searchLoading && suggestIdx === i && (
            <span className="absolute right-2 top-2">
              <Loader2 size={14} className="animate-spin text-gray-400" />
            </span>
          )}
          {suggestIdx === i && suggestions.length > 0 && (
            <div className="absolute top-full left-0 mt-1 w-72 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 max-h-52 overflow-y-auto">
              {suggestions.map((s, si) => (
                <button
                  key={si}
                  className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-blue-50 dark:hover:bg-blue-950 text-left"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSelectSuggestion(i, s);
                  }}
                >
                  <span className="flex flex-col">
                    <span className="font-medium text-gray-900 dark:text-gray-50">{s.name}</span>
                    <span className="text-gray-400 dark:text-gray-500 font-mono">{s.ticker}</span>
                  </span>
                  <span className="text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 rounded px-1.5 py-0.5 ml-2 shrink-0 text-xs">
                    {s.market}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </td>
      <td className="py-2 pr-3">
        <input
          type="number"
          inputMode="numeric"
          className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
          value={row.qty || ""}
          onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
          min={0}
          placeholder="0"
        />
      </td>
      <td className="py-2 pr-3">
        {overseas ? (
          <div>
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-400 shrink-0">$</span>
              <input
                type="number"
                inputMode="decimal"
                className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
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
            className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
            value={row.avg_price || ""}
            onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
            min={0}
            placeholder="0"
          />
        )}
      </td>
      <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
        {fmtKrwShort(row.invested_amount ?? 0)}원
      </td>
      <td className="py-2 pr-3">
        {overseas ? (
          <div className="relative">
            <span className="absolute left-2 top-2 text-xs text-gray-400 dark:text-gray-500 pointer-events-none">
              $
            </span>
            <input
              type="number"
              inputMode="decimal"
              className="w-full border border-gray-300 dark:border-gray-600 rounded pl-5 pr-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
              value={priceLoading ? "" : (rawRow.current_price_usd ?? "")}
              onChange={(e) => handleCurrentPriceUsd(i, e.target.value)}
              placeholder={priceLoading ? "조회중..." : "자동조회"}
              min={0}
              step="0.01"
              disabled={priceLoading}
            />
            {priceLoading && (
              <span className="absolute right-2 top-2">
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
              className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
              value={priceLoading ? "" : (rawRow.current_price ?? "")}
              onChange={(e) =>
                setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })
              }
              placeholder={priceLoading ? "조회중..." : "자동조회"}
              min={0}
              disabled={priceLoading}
            />
            {priceLoading && (
              <span className="absolute right-2 top-2">
                <Loader2 size={14} className="animate-spin text-blue-400" />
              </span>
            )}
          </div>
        )}
      </td>
      <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
        {fmtKrwShort(row.value_amount ?? 0)}원
      </td>
      <td className="py-2 pr-3">
        <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
      </td>
      <td className="py-2">
        <button
          onClick={() => removeRow(i)}
          className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-300 dark:text-gray-600 hover:text-red-500 rounded`}
        >
          <Trash2 size={16} />
        </button>
      </td>
    </tr>
  );
}
