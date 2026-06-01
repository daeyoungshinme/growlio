import { Loader2, Plus, Trash2 } from "lucide-react";
import type { StockSuggestion } from "../../api/assets";
import { fmtKrwShort } from "../../utils/format";

export interface Position {
  ticker: string;
  name: string;
  market: string;
  qty: number;
  avg_price: number;
  avg_price_usd: number | null;
  usd_rate: number | null;
  current_price: number | null;
  invested_amount?: number;
  value_amount?: number;
  pnl?: number;
  pnl_pct?: number;
}

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
}

const OVERSEAS = new Set(["NYSE", "NASDAQ", "AMEX"]);

const MARKETS = ["KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "AMEX"] as const;

function PnlCell({ val, pct }: { val: number; pct: number }) {
  const pos = val >= 0;
  return (
    <div className={`text-right text-xs ${pos ? "text-red-500" : "text-blue-500"}`}>
      <div className="font-semibold">{pos ? "+" : ""}{fmtKrwShort(val)}원</div>
      <div>{pos ? "+" : ""}{pct.toFixed(2)}%</div>
    </div>
  );
}

function SuggestionDropdown({ i, suggestions, onSelect }: {
  i: number;
  suggestions: StockSuggestion[];
  onSelect: (i: number, s: StockSuggestion) => void;
}) {
  return (
    <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 max-h-52 overflow-y-auto">
      {suggestions.map((s, si) => (
        <button
          key={si}
          className="w-full flex items-center justify-between px-3 py-2.5 text-sm hover:bg-blue-50 dark:hover:bg-blue-950 text-left"
          onMouseDown={(e) => { e.preventDefault(); onSelect(i, s); }}
        >
          <span className="flex flex-col">
            <span className="font-medium text-gray-900 dark:text-gray-50">{s.name}</span>
            <span className="text-gray-400 dark:text-gray-500 font-mono text-xs">{s.ticker}</span>
          </span>
          <span className="text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 rounded px-2 py-0.5 ml-2 shrink-0 text-xs">{s.market}</span>
        </button>
      ))}
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
      {MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
    </select>
  );
}

export function PositionsTable({
  rows, liveRows, readonly, usdRate,
  suggestions, suggestIdx, searchLoading, priceLoadingRows,
  setSuggestIdx, handleNameChange, handleNameBlur, handleSelectSuggestion,
  setRow, removeRow, addRow, handleAvgPriceUsd,
}: Props) {
  const handleMarketChange = (i: number, newMarket: string, currentMarket: string) => {
    const wasOverseas = OVERSEAS.has(currentMarket);
    const nowOverseas = OVERSEAS.has(newMarket);
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
        {liveRows.map((row, i) => {
          const overseas = OVERSEAS.has(row.market);
          const priceLoading = priceLoadingRows.has(i);
          return (
            <div key={i} className="py-4 space-y-3">
              <div className="relative">
                <input
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                  value={row.name}
                  onChange={(e) => handleNameChange(i, e.target.value)}
                  onFocus={() => { if (row.name && suggestions.length) setSuggestIdx(i); }}
                  onBlur={() => handleNameBlur(i)}
                  placeholder="종목명 또는 코드 검색..."
                  autoComplete="off"
                  disabled={readonly}
                />
                {searchLoading && suggestIdx === i && (
                  <span className="absolute right-3 top-3">
                    <Loader2 size={14} className="animate-spin text-gray-400" />
                  </span>
                )}
                {suggestIdx === i && suggestions.length > 0 && (
                  <SuggestionDropdown i={i} suggestions={suggestions} onSelect={handleSelectSuggestion} />
                )}
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {row.ticker && <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">{row.ticker}</span>}
                  <select
                    className="text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded-lg px-2 py-1.5 focus:outline-none disabled:opacity-50"
                    value={row.market}
                    disabled={readonly}
                    onChange={(e) => handleMarketChange(i, e.target.value, row.market)}
                  >
                    {MARKETS.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                </div>
                {!readonly && (
                  <button onClick={() => removeRow(i)} className="p-2 text-gray-300 dark:text-gray-600 hover:text-red-500 rounded-lg">
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">보유수량</p>
                  <input type="number"
                    className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                    value={row.qty || ""} onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
                    min={0} placeholder="0" disabled={readonly} />
                </div>
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">평단가</p>
                  {overseas ? (
                    <div>
                      <div className="flex items-center gap-1">
                        <span className="text-sm text-gray-400 shrink-0">$</span>
                        <input type="number"
                          className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                          value={row.avg_price_usd ?? ""} onChange={(e) => handleAvgPriceUsd(i, e.target.value)}
                          placeholder="0.00" min={0} step="0.01" disabled={readonly} />
                      </div>
                      {usdRate && (row.avg_price_usd ?? 0) > 0 && (
                        <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                          ≈ ₩{Math.floor((row.avg_price_usd ?? 0) * usdRate).toLocaleString()}
                        </div>
                      )}
                    </div>
                  ) : (
                    <input type="number"
                      className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                      value={row.avg_price || ""} onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
                      min={0} placeholder="0" disabled={readonly} />
                  )}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">현재가(원)</p>
                  <div className="relative">
                    <input type="number"
                      className="w-full border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2.5 text-sm text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                      value={priceLoading ? "" : (rows[i].current_price ?? "")}
                      onChange={(e) => setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })}
                      placeholder={priceLoading ? "조회중..." : "자동조회"} min={0} disabled={priceLoading} />
                    {priceLoading && <span className="absolute right-3 top-3"><Loader2 size={14} className="animate-spin text-blue-400" /></span>}
                  </div>
                </div>
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">매입금액</p>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300 pt-2.5 text-right">{fmtKrwShort(row.invested_amount ?? 0)}원</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 pb-1">
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">평가금액</p>
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{fmtKrwShort(row.value_amount ?? 0)}원</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mb-1">수익률</p>
                  <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── 데스크탑 테이블 뷰 (sm 이상) ── */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700">
              <th className="text-left pb-2 pr-3 font-medium w-52">종목명</th>
              <th className="text-right pb-2 pr-3 font-medium w-24">보유수량</th>
              <th className="text-right pb-2 pr-3 font-medium w-32">평단가</th>
              <th className="text-right pb-2 pr-3 font-medium">매입금액</th>
              <th className="text-right pb-2 pr-3 font-medium w-32">현재가(원)</th>
              <th className="text-right pb-2 pr-3 font-medium">평가금액</th>
              <th className="text-right pb-2 font-medium">수익률</th>
              <th className="w-8" />
            </tr>
          </thead>
          <tbody>
            {liveRows.map((row, i) => {
              const overseas = OVERSEAS.has(row.market);
              const priceLoading = priceLoadingRows.has(i);
              return (
                <tr key={i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 align-top">
                  <td className="py-2 pr-3">
                    <div className="relative">
                      <input
                        className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                        value={row.name}
                        onChange={(e) => handleNameChange(i, e.target.value)}
                        onFocus={() => { if (row.name && suggestions.length) setSuggestIdx(i); }}
                        onBlur={() => handleNameBlur(i)}
                        placeholder="종목명 또는 코드 검색..."
                        autoComplete="off"
                        disabled={readonly}
                      />
                      {(row.ticker || row.market !== "KOSPI") && (
                        <div className="flex items-center gap-1 mt-0.5">
                          {row.ticker && <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">{row.ticker}</span>}
                          {row.ticker && <span className="text-gray-300 dark:text-gray-600 text-xs">·</span>}
                          <MarketSelect value={row.market} disabled={readonly} onChange={(m) => handleMarketChange(i, m, row.market)} />
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
                      className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                      value={row.qty || ""} onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
                      min={0} placeholder="0" disabled={readonly} />
                  </td>
                  <td className="py-2 pr-3">
                    {overseas ? (
                      <div>
                        <div className="flex items-center gap-1">
                          <span className="text-xs text-gray-400 shrink-0">$</span>
                          <input type="number"
                            className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                            value={row.avg_price_usd ?? ""} onChange={(e) => handleAvgPriceUsd(i, e.target.value)}
                            placeholder="0.00" min={0} step="0.01" disabled={readonly} />
                        </div>
                        {usdRate && (row.avg_price_usd ?? 0) > 0 && (
                          <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                            ≈ ₩{Math.floor((row.avg_price_usd ?? 0) * usdRate).toLocaleString()}
                          </div>
                        )}
                      </div>
                    ) : (
                      <input type="number"
                        className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                        value={row.avg_price || ""} onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
                        min={0} placeholder="0" disabled={readonly} />
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    {fmtKrwShort(row.invested_amount ?? 0)}원
                  </td>
                  <td className="py-2 pr-3">
                    <div className="relative">
                      <input type="number"
                        className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                        value={priceLoading ? "" : (rows[i].current_price ?? "")}
                        onChange={(e) => setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })}
                        placeholder={priceLoading ? "조회중..." : "자동조회"} min={0} disabled={priceLoading} />
                      {priceLoading && <span className="absolute right-2 top-2"><Loader2 size={12} className="animate-spin text-blue-400" /></span>}
                    </div>
                  </td>
                  <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    {fmtKrwShort(row.value_amount ?? 0)}원
                  </td>
                  <td className="py-2 pr-3">
                    <PnlCell val={row.pnl ?? 0} pct={row.pnl_pct ?? 0} />
                  </td>
                  <td className="py-2">
                    {!readonly && (
                      <button onClick={() => removeRow(i)} className="p-1 text-gray-300 dark:text-gray-600 hover:text-red-500 rounded">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
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
