import { useEffect, useRef, useState } from "react";
import { Loader2, Plus, RefreshCw, Trash2, X } from "lucide-react";
import { api } from "../../api/client";
import { fetchExchangeRate, fetchStockPrice, searchStocks, StockSuggestion } from "../../api/assets";
import { extractErrorMessage } from "../../utils/error";
import { fmtKrwShort } from "../../utils/format";
import Modal from "../common/Modal";

interface Position {
  ticker: string;
  name: string;
  market: string;
  qty: number;
  avg_price: number;        // 항상 KRW
  avg_price_usd: number | null;
  usd_rate: number | null;
  current_price: number | null;  // 항상 KRW
  invested_amount?: number;
  value_amount?: number;
  pnl?: number;
  pnl_pct?: number;
}

interface Summary {
  total_invested: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
}

interface PositionsResponse {
  positions: Position[];
  summary: Summary;
}

const OVERSEAS = new Set(["NYSE", "NASDAQ", "AMEX"]);

const EMPTY_ROW: Position = {
  ticker: "", name: "", market: "KOSPI",
  qty: 0, avg_price: 0, avg_price_usd: null,
  usd_rate: null, current_price: null,
};


function PnlCell({ val, pct }: { val: number; pct: number }) {
  const pos = val >= 0;
  return (
    <div className={`text-right text-xs ${pos ? "text-red-500" : "text-blue-500"}`}>
      <div className="font-semibold">{pos ? "+" : ""}{fmtKrwShort(val)}원</div>
      <div>{pos ? "+" : ""}{pct.toFixed(2)}%</div>
    </div>
  );
}

export default function StockPositionsModal({
  accountId,
  accountName,
  onClose,
  readonly = false,
}: {
  accountId: string;
  accountName: string;
  onClose: () => void;
  readonly?: boolean;
}) {
  const [rows, setRows] = useState<Position[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [usdRate, setUsdRate] = useState<number | null>(null);

  // 자동완성
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([]);
  const [suggestIdx, setSuggestIdx] = useState<number | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 행별 현재가 로딩
  const [priceLoadingRows, setPriceLoadingRows] = useState<Set<number>>(new Set());

  useEffect(() => {
    api.get<PositionsResponse>(`/assets/${accountId}/positions`).then((r) => {
      setRows(r.data.positions.length ? r.data.positions : (readonly ? [] : [{ ...EMPTY_ROW }]));
      setSummary(r.data.summary);
    }).finally(() => setLoading(false));

    fetchExchangeRate().then((r) => setUsdRate(r.usd_krw)).catch(() => setUsdRate(1350));
  }, [accountId, readonly]);

  useEffect(() => {
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, []);

  const setRow = (i: number, patch: Partial<Position>) =>
    setRows((prev) => prev.map((r, idx) => idx === i ? { ...r, ...patch } : r));

  const addRow = () => setRows((prev) => [...prev, { ...EMPTY_ROW }]);
  const removeRow = (i: number) => {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
    if (suggestIdx === i) { setSuggestions([]); setSuggestIdx(null); }
  };

  // 현재가 자동 조회 (단일 행)
  const loadPrice = async (i: number, ticker: string, market: string) => {
    if (!ticker) return;
    setPriceLoadingRows((prev) => new Set([...prev, i]));
    try {
      const result = await fetchStockPrice(ticker, market);
      if (result.price_krw) {
        setRow(i, {
          current_price: result.price_krw,
          ...(result.usd_rate ? { usd_rate: result.usd_rate } : {}),
        });
      }
    } catch {
      // 조회 실패 시 무시
    } finally {
      setPriceLoadingRows((prev) => { const s = new Set(prev); s.delete(i); return s; });
    }
  };

  // 종목명 입력 → 디바운스 검색
  const handleNameChange = (i: number, value: string) => {
    setRow(i, { name: value });
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (!value.trim()) { setSuggestions([]); setSuggestIdx(null); return; }
    setSuggestIdx(i);
    searchTimer.current = setTimeout(async () => {
      setSearchLoading(true);
      try { setSuggestions(await searchStocks(value.trim())); }
      catch { setSuggestions([]); }
      finally { setSearchLoading(false); }
    }, 300);
  };

  // 종목 선택 → 티커·시장 자동 입력 + 현재가 자동 조회
  const handleSelectSuggestion = (i: number, s: StockSuggestion) => {
    setRows((prev) => prev.map((r, idx) => idx === i
      ? { ...r, ticker: s.ticker, name: s.name, market: s.market }
      : r
    ));
    setSuggestions([]);
    setSuggestIdx(null);
    loadPrice(i, s.ticker, s.market);
  };

  const handleNameBlur = (i: number) => {
    setTimeout(() => { if (suggestIdx === i) { setSuggestions([]); setSuggestIdx(null); } }, 150);
  };

  // 달러 평단가 입력
  const handleAvgPriceUsd = (i: number, usdVal: string) => {
    const usd = usdVal === "" ? 0 : parseFloat(usdVal) || 0;
    const krw = usdRate ? Math.round(usd * usdRate) : 0;
    setRow(i, { avg_price_usd: usd || null, usd_rate: usdRate, avg_price: krw });
  };

  // 실시간 합계 계산
  const liveRows = rows.map((r) => {
    const cur = r.current_price ?? r.avg_price;
    const invested = r.qty * r.avg_price;
    const value = r.qty * cur;
    const pnl = value - invested;
    const pnl_pct = invested ? (pnl / invested) * 100 : 0;
    return { ...r, current_price: cur, invested_amount: invested, value_amount: value, pnl, pnl_pct };
  });

  const liveSummary: Summary = liveRows.reduce(
    (acc, r) => ({
      total_invested: acc.total_invested + (r.invested_amount ?? 0),
      total_value: acc.total_value + (r.value_amount ?? 0),
      total_pnl: acc.total_pnl + (r.pnl ?? 0),
      total_pnl_pct: 0,
    }),
    { total_invested: 0, total_value: 0, total_pnl: 0, total_pnl_pct: 0 }
  );
  liveSummary.total_pnl_pct = liveSummary.total_invested
    ? (liveSummary.total_pnl / liveSummary.total_invested) * 100 : 0;

  const handleSave = async () => {
    const valid = rows.filter((r) => r.ticker && r.qty > 0 && r.avg_price > 0);
    if (!valid.length) { setError("종목명, 수량, 평단가를 입력하세요"); return; }
    setSaving(true); setError(null);
    try {
      const r = await api.put<PositionsResponse>(`/assets/${accountId}/positions`, valid);
      setRows(r.data.positions); setSummary(r.data.summary);
    } catch { setError("저장에 실패했습니다"); }
    finally { setSaving(false); }
  };

  const handleSyncAll = async () => {
    setSyncing(true); setError(null);
    try {
      const r = await api.post<PositionsResponse>(`/assets/${accountId}/positions/sync-prices`);
      setRows(r.data.positions); setSummary(r.data.summary);
    } catch (e: unknown) {
      setError(extractErrorMessage(e, "현재가 조회에 실패했습니다"));
    } finally { setSyncing(false); }
  };

  const displaySummary = summary ?? liveSummary;

  return (
    <Modal size="xl" onClose={onClose}>

        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-bold text-gray-900 dark:text-gray-50">종목 관리</h2>
            <p className="text-sm text-gray-400 dark:text-gray-500">{accountName}</p>
          </div>
          <div className="flex items-center gap-3">
            {usdRate && (
              <span className="text-xs text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5">
                USD/KRW <strong className="text-gray-600 dark:text-gray-300">{usdRate.toLocaleString(undefined, { maximumFractionDigits: 0 })}원</strong>
              </span>
            )}
            <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-gray-500 dark:text-gray-400"><X size={18} /></button>
          </div>
        </div>

        {/* KIS/LS 읽기전용 배너 */}
        {readonly && (
          <div className="px-6 py-2 bg-blue-50 dark:bg-blue-950 border-b border-blue-100 dark:border-blue-900 text-xs text-blue-600 dark:text-blue-400">
            KIS/LS 계좌는 동기화로 자동 업데이트됩니다. 종목을 직접 편집하려면 수동 계좌를 사용하세요.
          </div>
        )}

        {/* 요약 카드 */}
        <div className="grid grid-cols-4 gap-3 px-6 py-4 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 text-center text-sm">
          {[
            { label: "매입금액", val: displaySummary.total_invested, color: "" },
            { label: "평가금액", val: displaySummary.total_value, color: "" },
            { label: "평가손익", val: displaySummary.total_pnl, color: displaySummary.total_pnl >= 0 ? "text-red-500" : "text-blue-500" },
          ].map(({ label, val, color }) => (
            <div key={label}>
              <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">{label}</p>
              <p className={`font-bold ${color || "text-gray-900 dark:text-gray-50"}`}>
                {val >= 0 && color ? "+" : ""}{fmtKrwShort(val)}원
              </p>
            </div>
          ))}
          <div>
            <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">수익률</p>
            <p className={`font-bold text-xl ${displaySummary.total_pnl_pct >= 0 ? "text-red-500" : "text-blue-500"}`}>
              {displaySummary.total_pnl_pct >= 0 ? "+" : ""}{displaySummary.total_pnl_pct.toFixed(2)}%
            </p>
          </div>
        </div>

        {/* 종목 테이블 */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {loading ? (
            <div className="text-gray-400 dark:text-gray-500 text-sm py-8 text-center flex items-center justify-center gap-2">
              <Loader2 size={16} className="animate-spin" /> 불러오는 중...
            </div>
          ) : readonly && rows.length === 0 ? (
            <div className="text-gray-400 dark:text-gray-500 text-sm py-12 text-center">
              동기화 후 보유종목이 표시됩니다
            </div>
          ) : (
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

                      {/* 종목명 + 티커/시장 표시 + 자동완성 */}
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
                          {/* 티커 · 시장 표시 */}
                          {(row.ticker || row.market !== "KOSPI") && (
                            <div className="flex items-center gap-1 mt-0.5">
                              {row.ticker && (
                                <span className="text-xs text-gray-400 dark:text-gray-500 font-mono">{row.ticker}</span>
                              )}
                              {row.ticker && <span className="text-gray-300 dark:text-gray-600 text-xs">·</span>}
                              <select
                                className="text-xs text-gray-400 dark:text-gray-500 border-0 bg-transparent p-0 cursor-pointer focus:outline-none"
                                value={row.market}
                                onChange={(e) => {
                                  const newMarket = e.target.value;
                                  const wasOverseas = OVERSEAS.has(row.market);
                                  const nowOverseas = OVERSEAS.has(newMarket);
                                  if (wasOverseas !== nowOverseas) {
                                    setRow(i, { market: newMarket, avg_price: 0, avg_price_usd: null, usd_rate: null });
                                  } else {
                                    setRow(i, { market: newMarket });
                                  }
                                }}
                              >
                                <option value="KOSPI">KOSPI</option>
                                <option value="KOSDAQ">KOSDAQ</option>
                                <option value="NYSE">NYSE</option>
                                <option value="NASDAQ">NASDAQ</option>
                                <option value="AMEX">AMEX</option>
                              </select>
                            </div>
                          )}
                          {/* 검색 중 인디케이터 */}
                          {searchLoading && suggestIdx === i && (
                            <span className="absolute right-2 top-2">
                              <Loader2 size={12} className="animate-spin text-gray-400" />
                            </span>
                          )}
                          {/* 자동완성 드롭다운 */}
                          {suggestIdx === i && suggestions.length > 0 && (
                            <div className="absolute top-full left-0 mt-1 w-72 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-50 max-h-52 overflow-y-auto">
                              {suggestions.map((s, si) => (
                                <button
                                  key={si}
                                  className="w-full flex items-center justify-between px-3 py-2 text-xs hover:bg-blue-50 dark:hover:bg-blue-950 text-left"
                                  onMouseDown={(e) => { e.preventDefault(); handleSelectSuggestion(i, s); }}
                                >
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

                      {/* 보유수량 */}
                      <td className="py-2 pr-3">
                        <input
                          type="number"
                          className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                          value={row.qty || ""}
                          onChange={(e) => setRow(i, { qty: Number(e.target.value) })}
                          min={0}
                          placeholder="0"
                          disabled={readonly}
                        />
                      </td>

                      {/* 평단가 — 해외: 달러 입력, 국내: 원화 입력 */}
                      <td className="py-2 pr-3">
                        {overseas ? (
                          <div>
                            <div className="flex items-center gap-1">
                              <span className="text-xs text-gray-400 shrink-0">$</span>
                              <input
                                type="number"
                                className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                                value={row.avg_price_usd ?? ""}
                                onChange={(e) => handleAvgPriceUsd(i, e.target.value)}
                                placeholder="0.00"
                                min={0}
                                step="0.01"
                                disabled={readonly}
                              />
                            </div>
                            {usdRate && (row.avg_price_usd ?? 0) > 0 && (
                              <div className="text-xs text-gray-400 dark:text-gray-500 text-right mt-0.5">
                                ≈ ₩{Math.round((row.avg_price_usd ?? 0) * usdRate).toLocaleString()}
                              </div>
                            )}
                          </div>
                        ) : (
                          <input
                            type="number"
                            className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:text-gray-500"
                            value={row.avg_price || ""}
                            onChange={(e) => setRow(i, { avg_price: Number(e.target.value) })}
                            min={0}
                            placeholder="0"
                            disabled={readonly}
                          />
                        )}
                      </td>

                      {/* 매입금액 (자동계산) */}
                      <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
                        {fmtKrwShort(row.invested_amount ?? 0)}원
                      </td>

                      {/* 현재가 — 자동조회 or 수동 입력 */}
                      <td className="py-2 pr-3">
                        <div className="relative">
                          <input
                            type="number"
                            className="w-full border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 text-xs text-right bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50"
                            value={priceLoading ? "" : (rows[i].current_price ?? "")}
                            onChange={(e) => setRow(i, { current_price: e.target.value ? Number(e.target.value) : null })}
                            placeholder={priceLoading ? "조회중..." : "자동조회"}
                            min={0}
                            disabled={priceLoading}
                          />
                          {priceLoading && (
                            <span className="absolute right-2 top-2">
                              <Loader2 size={12} className="animate-spin text-blue-400" />
                            </span>
                          )}
                        </div>
                      </td>

                      {/* 평가금액 (자동계산) */}
                      <td className="py-2 pr-3 text-right text-xs text-gray-700 dark:text-gray-300 whitespace-nowrap">
                        {fmtKrwShort(row.value_amount ?? 0)}원
                      </td>

                      {/* 수익률 (자동계산) */}
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
          )}

          {!readonly && (
            <button
              onClick={addRow}
              className="mt-3 flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 font-medium"
            >
              <Plus size={14} />
              종목 추가
            </button>
          )}
        </div>

        {error && (
          <div className="mx-6 mb-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        {/* 하단 버튼 */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-b-2xl">
          <button
            onClick={handleSyncAll}
            disabled={syncing || rows.every((r) => !r.ticker)}
            className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 px-4 py-2 rounded-lg hover:bg-white dark:hover:bg-gray-700 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
            전체 현재가 갱신
          </button>
          <div className="flex gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-white dark:hover:bg-gray-700">닫기</button>
            {!readonly && (
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-5 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
              >
                {saving ? "저장 중..." : "저장"}
              </button>
            )}
          </div>
        </div>
    </Modal>
  );
}
