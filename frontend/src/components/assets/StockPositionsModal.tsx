import { useEffect, useState } from "react";
import { Loader2, RefreshCw, X } from "lucide-react";
import { api } from "../../api/client";
import { fetchStockPrice } from "../../api/assets";
import { useExchangeRate } from "../../hooks/useExchangeRate";
import { useStockSearch } from "../../hooks/useStockSearch";
import { isOverseasMarket } from "../../constants/markets";
import { extractErrorMessage } from "../../utils/error";
import { toast } from "../../utils/toast";
import { fmtKrwShort } from "../../utils/format";
import { pnlColor } from "../../utils/colors";
import Modal from "../common/Modal";
import { PositionsTable, type Position } from "./PositionsTable";

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

const EMPTY_ROW: Position = {
  ticker: "", name: "", market: "KOSPI",
  qty: 0, avg_price: 0, avg_price_usd: null,
  usd_rate: null, current_price: null, current_price_usd: null,
};

const enrichPositions = (positions: Position[]): Position[] =>
  positions.map((p) => ({
    ...p,
    current_price_usd:
      isOverseasMarket(p.market) && p.current_price && p.usd_rate
        ? +(p.current_price / p.usd_rate).toFixed(4)
        : (p.current_price_usd ?? null),
  }));

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
  const usdRate = useExchangeRate();

  const { suggestions, isSearching: searchLoading, search: runStockSearch, clearSuggestions } = useStockSearch();
  const [suggestIdx, setSuggestIdx] = useState<number | null>(null);
  const [priceLoadingRows, setPriceLoadingRows] = useState<Set<number>>(new Set());

  useEffect(() => {
    api.get<PositionsResponse>(`/assets/${accountId}/positions`).then((r) => {
      const positions = r.data.positions;
      setRows(enrichPositions(positions.length ? positions : (readonly ? [] : [{ ...EMPTY_ROW }])));
      setSummary(r.data.summary);
    }).catch((e) => {
      setError(extractErrorMessage(e, "포지션 조회에 실패했습니다"));
    }).finally(() => setLoading(false));
  }, [accountId, readonly]);

  const setRow = (i: number, patch: Partial<Position>) =>
    setRows((prev) => prev.map((r, idx) => idx === i ? { ...r, ...patch } : r));

  const addRow = () => setRows((prev) => [...prev, { ...EMPTY_ROW }]);

  const removeRow = (i: number) => {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
    if (suggestIdx === i) { clearSuggestions(); setSuggestIdx(null); }
  };

  const loadPrice = async (i: number, ticker: string, market: string) => {
    if (!ticker) return;
    setPriceLoadingRows((prev) => new Set([...prev, i]));
    try {
      const result = await fetchStockPrice(ticker, market);
      if (result.price_krw) {
        setRow(i, {
          current_price: result.price_krw,
          current_price_usd: result.price_usd ?? null,
          ...(result.usd_rate ? { usd_rate: result.usd_rate } : {}),
        });
      }
    } catch (e: unknown) {
      toast(extractErrorMessage(e, "현재가 조회에 실패했습니다"));
    } finally {
      setPriceLoadingRows((prev) => { const s = new Set(prev); s.delete(i); return s; });
    }
  };

  const handleNameChange = (i: number, value: string) => {
    setRow(i, { name: value });
    if (!value.trim()) { clearSuggestions(); setSuggestIdx(null); return; }
    setSuggestIdx(i);
    runStockSearch(value);
  };

  const handleSelectSuggestion = (i: number, s: { ticker: string; name: string; market: string }) => {
    setRows((prev) => prev.map((r, idx) => idx === i
      ? { ...r, ticker: s.ticker, name: s.name, market: s.market }
      : r
    ));
    clearSuggestions();
    setSuggestIdx(null);
    loadPrice(i, s.ticker, s.market);
  };

  const handleNameBlur = (i: number) => {
    setTimeout(() => { if (suggestIdx === i) { clearSuggestions(); setSuggestIdx(null); } }, 150);
  };

  const handleAvgPriceUsd = (i: number, usdVal: string) => {
    const usd = usdVal === "" ? 0 : parseFloat(usdVal) || 0;
    const krw = usdRate ? Math.floor(usd * usdRate) : 0;
    setRow(i, { avg_price_usd: usd || null, usd_rate: usdRate, avg_price: krw });
  };

  const handleCurrentPriceUsd = (i: number, usdVal: string) => {
    const usd = usdVal === "" ? null : parseFloat(usdVal) || null;
    const krw = usd && usdRate ? Math.round(usd * usdRate) : null;
    setRow(i, { current_price_usd: usd, current_price: krw });
  };

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
  if (liveSummary.total_invested > 0) {
    liveSummary.total_pnl_pct = (liveSummary.total_pnl / liveSummary.total_invested) * 100;
  }

  const handleSave = async () => {
    const valid = rows.filter((r) => r.ticker || r.name || r.qty || r.avg_price);
    setSaving(true); setError(null);
    try {
      const r = await api.put<PositionsResponse>(`/assets/${accountId}/positions`, valid);
      setRows(enrichPositions(r.data.positions)); setSummary(r.data.summary);
    } catch { setError("저장에 실패했습니다"); }
    finally { setSaving(false); }
  };

  const handleSyncAll = async () => {
    setSyncing(true); setError(null);
    try {
      const r = await api.post<PositionsResponse>(`/assets/${accountId}/positions/sync-prices`);
      setRows(enrichPositions(r.data.positions)); setSummary(r.data.summary);
    } catch (e: unknown) {
      setError(extractErrorMessage(e, "현재가 조회에 실패했습니다"));
    } finally { setSyncing(false); }
  };

  const displaySummary = summary ?? liveSummary;

  return (
    <Modal size="xl" onClose={onClose}>
      {/* 헤더 */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h2 className="text-base font-bold text-gray-900 dark:text-gray-50">종목 관리</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500">{accountName}</p>
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

      {/* KIS 읽기전용 배너 */}
      {readonly && (
        <div className="px-6 py-2 bg-blue-50 dark:bg-blue-950 border-b border-blue-100 dark:border-blue-900 text-xs text-blue-600 dark:text-blue-400">
          KIS/LS 계좌는 동기화로 자동 업데이트됩니다. 종목을 직접 편집하려면 수동 계좌를 사용하세요.
        </div>
      )}

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2 px-4 sm:px-6 py-2 sm:py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 text-center text-sm">
        <div>
          <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">매입금액</p>
          <p className="font-bold text-sm text-gray-900 dark:text-gray-50">
            {fmtKrwShort(displaySummary.total_invested)}원
          </p>
        </div>
        <div>
          <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">평가금액</p>
          <p className="font-bold text-sm text-gray-900 dark:text-gray-50">
            {fmtKrwShort(displaySummary.total_value)}원
          </p>
        </div>
        <div>
          <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">손익/수익률</p>
          <p className={`font-bold text-sm ${pnlColor(displaySummary.total_pnl)}`}>
            {displaySummary.total_pnl >= 0 ? "+" : ""}{fmtKrwShort(displaySummary.total_pnl)}원
          </p>
          <p className={`text-xs ${pnlColor(displaySummary.total_pnl_pct)}`}>
            {displaySummary.total_pnl_pct >= 0 ? "+" : ""}{displaySummary.total_pnl_pct.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* 종목 목록 */}
      <div className="flex-1 min-h-0 overflow-auto px-4 sm:px-6 py-2">
        {loading ? (
          <div className="text-gray-400 dark:text-gray-500 text-sm py-8 text-center flex items-center justify-center gap-2">
            <Loader2 size={16} className="animate-spin" /> 불러오는 중...
          </div>
        ) : readonly && rows.length === 0 ? (
          <div className="text-gray-400 dark:text-gray-500 text-sm py-12 text-center">
            동기화 후 보유종목이 표시됩니다
          </div>
        ) : (
          <PositionsTable
            rows={rows}
            liveRows={liveRows}
            readonly={readonly}
            usdRate={usdRate}
            suggestions={suggestions}
            suggestIdx={suggestIdx}
            searchLoading={searchLoading}
            priceLoadingRows={priceLoadingRows}
            setSuggestIdx={setSuggestIdx}
            handleNameChange={handleNameChange}
            handleNameBlur={handleNameBlur}
            handleSelectSuggestion={handleSelectSuggestion}
            setRow={setRow}
            removeRow={removeRow}
            addRow={addRow}
            handleAvgPriceUsd={handleAvgPriceUsd}
            handleCurrentPriceUsd={handleCurrentPriceUsd}
          />
        )}
      </div>

      {error && (
        <div className="mx-6 mb-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* 하단 버튼 */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-b-2xl">
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
