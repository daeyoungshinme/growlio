import { useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import type { StockSuggestion } from "../../api/assets";
import { convertUsdToKrw, fmtKrwShort } from "../../utils/format";
import { isOverseasMarket, POSITION_MARKETS } from "../../constants/markets";
import PriceCell from "../common/PriceCell";
import { SuggestionDropdown } from "../common/SuggestionDropdown";
import { pnlColor } from "../../utils/colors";
import type { Position } from "../../hooks/usePositionsEditor";

export type { Position };

interface Props {
  rows: Position[];
  liveRows: Position[];
  readonly: boolean;
  usdRate: number | null;
  suggestions: StockSuggestion[];
  suggestIdx: number | null;
  searchLoading: boolean;
  priceLoadingRows: Set<number>;
  setSuggestIdx: (idx: number | null) => void;
  handleNameChange: (i: number, value: string) => void;
  handleNameBlur: (i: number) => void;
  handleSelectSuggestion: (i: number, s: StockSuggestion) => void;
  setRow: (i: number, patch: Partial<Position>) => void;
  removeRow: (i: number) => void;
  addRow: () => void;
  handleAvgPriceUsd: (i: number, usdVal: string) => void;
  handleCurrentPriceUsd: (i: number, usdVal: string) => void;
}

function PnlCell({ val, pct }: { val: number; pct: number }) {
  const color = pnlColor(val);
  return (
    <div className="text-right text-xs">
      <div className={`font-bold ${color}`}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</div>
      <div className={color}>{val >= 0 ? "+" : ""}{fmtKrwShort(val)}원</div>
    </div>
  );
}

function MarketSelect({ value, disabled, onChange }: {
  value: string;
  disabled: boolean;
  onChange: (market: string) => void;
}) {
  return (
    <select
      className="text-xs text-gray-400 dark:text-gray-500 border-0 bg-transparent p-0 cursor-pointer focus:outline-none"
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {POSITION_MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
    </select>
  );
}

function ReadonlyMobileCard({ row }: { row: Position }) {
  const overseas = isOverseasMarket(row.market);
  const pnl = row.pnl ?? 0;
  const pnlPct = row.pnl_pct ?? 0;
  const color = pnlColor(pnl);

  return (
    <div className="px-4 py-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-xs text-gray-900 dark:text-gray-50 truncate">{row.name || "—"}</p>
          <div className="flex items-center gap-1.5 mt-0.5">
            {row.ticker && <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">{row.ticker}</span>}
            <span className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded">{row.market}</span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="font-semibold text-xs text-gray-900 dark:text-gray-50">{fmtKrwShort(row.value_amount ?? 0)}원</p>
          <p className={`text-xs font-semibold mt-0.5 ${color}`}>{pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%</p>
          <p className={`text-xs ${color}`}>{pnl >= 0 ? "+" : ""}{fmtKrwShort(pnl)}원</p>
        </div>
      </div>
      <div className="mt-1.5 pt-1.5 border-t border-gray-100 dark:border-gray-800 grid grid-cols-3 gap-x-2">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">수량</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5">{row.qty.toLocaleString()}주</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">평단가</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5">
            {overseas && row.avg_price_usd ? `$${row.avg_price_usd.toFixed(2)}` : `${(row.avg_price ?? 0).toLocaleString()}원`}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">매입금액</p>
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5">{fmtKrwShort(row.invested_amount ?? 0)}원</p>
        </div>
      </div>
    </div>
  );
}

function ReadonlyDesktopRow({ row }: { row: Position }) {
  const overseas = isOverseasMarket(row.market);

  return (
    <tr className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50/50 dark:hover:bg-gray-800/50">
      <td className="py-3 pr-3">
        <p className="font-semibold text-sm text-gray-900 dark:text-gray-50">{row.name || "—"}</p>
        {(row.ticker || row.market !== "KOSPI") && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            {row.ticker}{row.ticker && " · "}{row.market}
          </p>
        )}
      </td>
      <td className="py-3 pr-3 text-right">
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{row.qty.toLocaleString()}</span>
      </td>
      <td className="py-3 pr-3 text-right">
        <PriceCell krw={row.avg_price} usd={row.avg_price_usd} isOverseas={overseas} />
      </td>
      <td className="py-3 pr-3 text-right text-sm font-medium text-gray-700 dark:text-gray-300 whitespace-nowrap">
        {fmtKrwShort(row.invested_amount ?? 0)}원
      </td>
      <td className="py-3 pr-3 text-right">
        <PriceCell krw={row.current_price} usd={row.current_price_usd} isOverseas={overseas} />
      </td>
      <td className="py-3 pr-3 text-right text-sm font-semibold text-gray-800 dark:text-gray-200 whitespace-nowrap">
        {fmtKrwShort(row.value_amount ?? 0)}원
      </td>
      <td className="py-3 pr-3">
        <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
      </td>
      <td className="py-3 w-8" />
    </tr>
  );
}

export function PositionsTable({
  rows, liveRows, readonly, usdRate,
  suggestions, suggestIdx, searchLoading, priceLoadingRows,
  setSuggestIdx, handleNameChange, handleNameBlur, handleSelectSuggestion,
  setRow, removeRow, addRow, handleAvgPriceUsd, handleCurrentPriceUsd,
}: Props) {
  const [activeInputEl, setActiveInputEl] = useState<HTMLInputElement | null>(null);

  const handleMarketChange = (i: number, newMarket: string, currentMarket: string) => {
    const wasOverseas = isOverseasMarket(currentMarket);
    const nowOverseas = isOverseasMarket(newMarket);
    if (wasOverseas !== nowOverseas) {
      setRow(i, { market: newMarket, avg_price: 0, avg_price_usd: null, usd_rate: null });
    } else {
      setRow(i, { market: newMarket });
    }
  };

  return (
    <>
      {/* ── 모바일 카드 뷰 (sm 미만) ── */}
      <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700">
        {readonly ? (
          liveRows.map((row, i) => <ReadonlyMobileCard key={i} row={row} />)
        ) : (
          liveRows.map((row, i) => {
            const overseas = isOverseasMarket(row.market);
            const priceLoading = priceLoadingRows.has(i);
            return (
              <div key={i} className="py-3 space-y-2">
                <div className="relative">
                  <input
                    className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-base bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                    value={row.name}
                    onChange={(e) => handleNameChange(i, e.target.value)}
                    onFocus={(e) => {
                      setActiveInputEl(e.currentTarget);
                      if (row.name && suggestions.length) setSuggestIdx(i);
                      const el = e.currentTarget;
                      setTimeout(() => el.scrollIntoView({ behavior: "smooth", block: "nearest" }), 300);
                    }}
                    onBlur={(e) => { setActiveInputEl(null); handleNameBlur(i); void e; }}
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
                      className="text-base border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg px-2 py-1 focus:outline-none"
                      value={row.market}
                      onChange={(e) => handleMarketChange(i, e.target.value, row.market)}
                    >
                      {POSITION_MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
                    </select>
                  </div>
                  <button onClick={() => removeRow(i)} className="p-1.5 text-gray-300 dark:text-gray-600 hover:text-red-500 rounded-lg">
                    <Trash2 size={16} />
                  </button>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">보유수량</p>
                    <input type="number"
                      className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                      value={row.qty || ""} onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
                      min={0} placeholder="0" />
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">평단가</p>
                    {overseas ? (
                      <div>
                        <div className="flex items-center gap-1">
                          <span className="text-sm text-gray-400 shrink-0">$</span>
                          <input type="number"
                            className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                            value={row.avg_price_usd ?? ""} onChange={(e) => handleAvgPriceUsd(i, e.target.value)}
                            placeholder="0.00" min={0} step="0.01" />
                        </div>
                        {convertUsdToKrw(row.avg_price_usd, usdRate) > 0 && (
                          <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                            ≈ ₩{convertUsdToKrw(row.avg_price_usd, usdRate).toLocaleString()}
                          </div>
                        )}
                      </div>
                    ) : (
                      <input type="number"
                        className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-2.5 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                        value={row.avg_price || ""} onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
                        min={0} placeholder="0" />
                    )}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">{overseas ? "현재가($)" : "현재가(원)"}</p>
                  {overseas ? (
                    <div className="relative">
                      <span className="absolute left-3 top-2 text-sm text-gray-400 dark:text-gray-500 pointer-events-none">$</span>
                      <input type="number"
                        className={`w-full border border-gray-300 dark:border-gray-600 rounded-lg pl-6 pr-3 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 transition-opacity ${priceLoading ? "opacity-50" : ""}`}
                        value={rows[i].current_price_usd ?? ""}
                        onChange={(e) => handleCurrentPriceUsd(i, e.target.value)}
                        placeholder="자동조회" min={0} step="0.01" disabled={priceLoading} />
                      {priceLoading && <span className="absolute right-3 top-2.5"><Loader2 size={14} className="animate-spin text-blue-400" /></span>}
                      {convertUsdToKrw(rows[i].current_price_usd, usdRate) > 0 && (
                        <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                          ≈ ₩{convertUsdToKrw(rows[i].current_price_usd, usdRate).toLocaleString()}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="relative">
                      <input type="number"
                        className={`w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 text-base text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 transition-opacity ${priceLoading ? "opacity-50" : ""}`}
                        value={rows[i].current_price ?? ""}
                        onChange={(e) => setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })}
                        placeholder="자동조회" min={0} disabled={priceLoading} />
                      {priceLoading && <span className="absolute right-3 top-2.5"><Loader2 size={14} className="animate-spin text-blue-400" /></span>}
                    </div>
                  )}
                </div>
                <div className="border-t border-gray-100 dark:border-gray-800 pt-2 grid grid-cols-3 gap-x-3 pb-1">
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500">매입금액</p>
                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5 text-right">{fmtKrwShort(row.invested_amount ?? 0)}원</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
                    <p className="text-xs font-medium text-gray-700 dark:text-gray-300 mt-0.5 text-right">{fmtKrwShort(row.value_amount ?? 0)}원</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-400 dark:text-gray-500">수익률</p>
                    <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* ── 데스크탑 테이블 뷰 (sm 이상) ── */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-50 dark:bg-gray-800 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2.5 pr-3 pl-1 font-medium w-52">종목명</th>
              <th className="text-right py-2.5 pr-3 font-medium w-24">보유수량</th>
              <th className="text-right py-2.5 pr-3 font-medium w-32">평단가</th>
              <th className="text-right py-2.5 pr-3 font-medium">매입금액</th>
              <th className="text-right py-2.5 pr-3 font-medium w-32">현재가</th>
              <th className="text-right py-2.5 pr-3 font-medium">평가금액</th>
              <th className="text-right py-2.5 font-medium">수익률</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {readonly ? (
              liveRows.map((row, i) => <ReadonlyDesktopRow key={i} row={row} />)
            ) : (
              liveRows.map((row, i) => {
                const overseas = isOverseasMarket(row.market);
                const priceLoading = priceLoadingRows.has(i);
                return (
                  <tr key={i} className="border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 align-top">
                    <td className="py-2 pr-3">
                      <div className="relative">
                        <input
                          className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                          value={row.name}
                          onChange={(e) => handleNameChange(i, e.target.value)}
                          onFocus={() => { if (row.name && suggestions.length) setSuggestIdx(i); }}
                          onBlur={() => handleNameBlur(i)}
                          placeholder="종목명 또는 코드 검색..."
                          autoComplete="off"
                        />
                        {(row.ticker || row.market !== "KOSPI") && (
                          <div className="flex items-center gap-1 mt-0.5">
                            {row.ticker && <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">{row.ticker}</span>}
                            {row.ticker && <span className="text-gray-300 dark:text-gray-600 text-xs">·</span>}
                            <MarketSelect value={row.market} disabled={false} onChange={(m) => handleMarketChange(i, m, row.market)} />
                          </div>
                        )}
                        {searchLoading && suggestIdx === i && <span className="absolute right-2 top-2"><Loader2 size={12} className="animate-spin text-gray-400" /></span>}
                        {suggestIdx === i && suggestions.length > 0 && (
                          <div className="absolute top-full left-0 mt-1 w-72 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 max-h-52 overflow-y-auto">
                            {suggestions.map((s, si) => (
                              <button key={si}
                                className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-blue-50 dark:hover:bg-blue-950 text-left"
                                onMouseDown={(e) => { e.preventDefault(); handleSelectSuggestion(i, s); }}>
                                <span className="flex flex-col">
                                  <span className="font-medium text-gray-900 dark:text-gray-50">{s.name}</span>
                                  <span className="text-gray-400 dark:text-gray-500 font-mono">{s.ticker}</span>
                                </span>
                                <span className="text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 rounded px-1.5 py-0.5 ml-2 shrink-0 text-xs">{s.market}</span>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <input type="number"
                        className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                        value={row.qty || ""} onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
                        min={0} placeholder="0" />
                    </td>
                    <td className="py-2 pr-3">
                      {overseas ? (
                        <div>
                          <div className="flex items-center gap-1">
                            <span className="text-xs text-gray-400 shrink-0">$</span>
                            <input type="number"
                              className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                              value={row.avg_price_usd ?? ""} onChange={(e) => handleAvgPriceUsd(i, e.target.value)}
                              placeholder="0.00" min={0} step="0.01" />
                          </div>
                          {convertUsdToKrw(row.avg_price_usd, usdRate) > 0 && (
                            <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                              ≈ ₩{convertUsdToKrw(row.avg_price_usd, usdRate).toLocaleString()}
                            </div>
                          )}
                        </div>
                      ) : (
                        <input type="number"
                          className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                          value={row.avg_price || ""} onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
                          min={0} placeholder="0" />
                      )}
                    </td>
                    <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
                      {fmtKrwShort(row.invested_amount ?? 0)}원
                    </td>
                    <td className="py-2 pr-3">
                      {overseas ? (
                        <div className="relative">
                          <span className="absolute left-2 top-2 text-xs text-gray-400 dark:text-gray-500 pointer-events-none">$</span>
                          <input type="number"
                            className="w-full border border-gray-300 dark:border-gray-600 rounded pl-5 pr-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                            value={priceLoading ? "" : (rows[i].current_price_usd ?? "")}
                            onChange={(e) => handleCurrentPriceUsd(i, e.target.value)}
                            placeholder={priceLoading ? "조회중..." : "자동조회"} min={0} step="0.01" disabled={priceLoading} />
                          {priceLoading && <span className="absolute right-2 top-2"><Loader2 size={12} className="animate-spin text-blue-400" /></span>}
                          {convertUsdToKrw(rows[i].current_price_usd, usdRate) > 0 && (
                            <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                              ≈ ₩{convertUsdToKrw(rows[i].current_price_usd, usdRate).toLocaleString()}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="relative">
                          <input type="number"
                            className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                            value={priceLoading ? "" : (rows[i].current_price ?? "")}
                            onChange={(e) => setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })}
                            placeholder={priceLoading ? "조회중..." : "자동조회"} min={0} disabled={priceLoading} />
                          {priceLoading && <span className="absolute right-2 top-2"><Loader2 size={12} className="animate-spin text-blue-400" /></span>}
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
                      <button onClick={() => removeRow(i)} className="p-1 text-gray-300 dark:text-gray-600 hover:text-red-500 rounded">
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {!readonly && (
        <button onClick={addRow}
          className="mt-3 flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium">
          <Plus size={14} /> 종목 추가
        </button>
      )}
    </>
  );
}
