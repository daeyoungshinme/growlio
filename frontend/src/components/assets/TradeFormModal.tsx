import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import Modal from "@/components/common/Modal";
import type { AssetAccount } from "@/api/assets";
import {
  createTrade,
  deleteTrade,
  fetchTrades,
  updateTrade,
  type TradeRecord,
  type TradeSide,
  type TradeUpdate,
} from "@/api/trades";
import { tradeSchema } from "@/schemas/trade";
import { useStockSearch } from "@/hooks/useStockSearch";
import { useExchangeRateContext } from "@/context/ExchangeRateContext";
import { isOverseasMarket } from "@/constants/markets";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { FORM_LABEL, INPUT_SM } from "@/constants/inputStyles";
import {
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
  TOUCH_TARGET_MIN,
  TOUCH_TARGET_ROW,
} from "@/constants/uiSizes";
import { invalidateTradeData } from "@/utils/queryInvalidation";
import { convertUsdToKrw, fmtKrwPrice, localToday } from "@/utils/format";
import { extractErrorMessage } from "@/utils/error";
import { toast } from "@/utils/toast";

export interface TradePrefill {
  account_id: string;
  ticker: string;
  market: string;
  name: string;
}

interface Props {
  accounts: AssetAccount[];
  prefill?: TradePrefill | null;
  onClose: () => void;
}

const SIDE_OPTIONS: { value: TradeSide; label: string }[] = [
  { value: "BUY", label: "매수" },
  { value: "SELL", label: "매도" },
];

export default function TradeFormModal({ accounts, prefill, onClose }: Props) {
  const qc = useQueryClient();
  const { rate } = useExchangeRateContext();
  const [accountId, setAccountId] = useState(prefill?.account_id ?? accounts[0]?.id ?? "");
  const [side, setSide] = useState<TradeSide>("BUY");
  const [stock, setStock] = useState<{ ticker: string; market: string; name: string } | null>(
    prefill ? { ticker: prefill.ticker, market: prefill.market, name: prefill.name } : null,
  );
  const [query, setQuery] = useState("");
  const [qty, setQty] = useState("");
  const [price, setPrice] = useState("");
  const [fee, setFee] = useState("");
  const [tradeDate, setTradeDate] = useState(localToday());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  // 기존 기록 수정 중이면 그 기록 — 수정 시 단가는 저장된 원화 그대로 다룬다(해외도 USD 역환산 없음)
  const [editing, setEditing] = useState<TradeRecord | null>(null);
  const { suggestions, isSearching, search, clearSuggestions } = useStockSearch();

  const overseas = stock ? isOverseasMarket(stock.market) : false;
  const priceInUsd = overseas && !editing;

  const { data: records = [] } = useQuery<TradeRecord[]>({
    queryKey: QUERY_KEYS.tradesFor(accountId, stock?.ticker ?? "", stock?.market ?? ""),
    queryFn: () =>
      fetchTrades({ account_id: accountId, ticker: stock?.ticker, market: stock?.market }),
    enabled: !!accountId && !!stock,
  });

  const createMut = useMutation({
    mutationFn: createTrade,
    onSuccess: () => {
      void invalidateTradeData(qc);
      toast("매매 기록을 저장했습니다", "success");
      setQty("");
      setPrice("");
      setFee("");
      setNotes("");
    },
    onError: (e) => setError(extractErrorMessage(e, "저장에 실패했습니다")),
  });

  const resetFields = () => {
    setQty("");
    setPrice("");
    setFee("");
    setNotes("");
    setSide("BUY");
    setTradeDate(localToday());
  };

  const startEdit = (r: TradeRecord) => {
    setEditing(r);
    setError(null);
    setSide(r.side);
    setQty(String(r.qty));
    setPrice(String(r.price_krw));
    setFee(r.fee != null ? String(r.fee) : "");
    setTradeDate(r.trade_date);
    setNotes(r.notes ?? "");
  };

  const cancelEdit = () => {
    setEditing(null);
    resetFields();
  };

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: TradeUpdate }) => updateTrade(id, data),
    onSuccess: () => {
      void invalidateTradeData(qc);
      toast("매매 기록을 수정했습니다", "success");
      cancelEdit();
    },
    onError: (e) => setError(extractErrorMessage(e, "수정에 실패했습니다")),
  });

  const deleteMut = useMutation({
    mutationFn: deleteTrade,
    onSuccess: () => void invalidateTradeData(qc),
    onError: (e) => toast(extractErrorMessage(e, "삭제에 실패했습니다"), "error"),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const rawPrice = Number(price);
    if (priceInUsd && !rate) {
      setError("환율 정보를 불러오지 못해 해외 종목 단가를 원화로 환산할 수 없습니다");
      return;
    }
    const priceKrw = priceInUsd ? convertUsdToKrw(rawPrice, rate) : rawPrice;
    const parsed = tradeSchema.safeParse({
      account_id: accountId,
      side,
      ticker: stock?.ticker ?? "",
      market: stock?.market ?? "",
      qty: qty === "" ? undefined : Number(qty),
      price_krw: price === "" ? undefined : priceKrw,
      fee: fee === "" ? undefined : Number(fee),
      trade_date: tradeDate,
      notes: notes || undefined,
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "입력값을 확인해주세요");
      return;
    }
    if (editing) {
      const { side: s2, qty: q, price_krw, fee: f, trade_date, notes: n } = parsed.data;
      updateMut.mutate({
        id: editing.id,
        // 비운 수수료·메모는 null로 보내야 기존 값이 지워진다(undefined면 JSON에서 빠져 유지됨)
        data: { side: s2, qty: q, price_krw, fee: f ?? null, trade_date, notes: n ?? null },
      });
      return;
    }
    createMut.mutate({ ...parsed.data, name: stock?.name ?? "" });
  };

  return (
    <Modal title="매매 기록" onClose={onClose} size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          기록한 종목은 스냅샷 추정 대신 이 기록으로 기간별 매수·수익률을 계산합니다. 보유 종목
          수량은 바뀌지 않습니다.
        </p>

        <div>
          <label htmlFor="trade-account" className={FORM_LABEL}>
            계좌
          </label>
          <select
            id="trade-account"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            disabled={!!prefill}
            className={`${INPUT_SM} w-full`}
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex gap-2" role="group" aria-label="매매 구분">
          {SIDE_OPTIONS.map((o) => (
            <button
              key={o.value}
              type="button"
              aria-pressed={side === o.value}
              onClick={() => setSide(o.value)}
              className={`${TOUCH_TARGET_MIN} flex-1 rounded-lg text-sm font-medium transition-colors ${
                side === o.value
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>

        <div>
          <label htmlFor="trade-stock" className={FORM_LABEL}>
            종목
          </label>
          {stock ? (
            <div className="flex items-center justify-between gap-2 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
              <span className="text-sm text-gray-900 dark:text-gray-50 truncate">
                {stock.name || stock.ticker}{" "}
                <span className="text-xs text-gray-400 dark:text-gray-500">
                  {stock.ticker} · {stock.market}
                </span>
              </span>
              {!prefill && (
                <button
                  type="button"
                  onClick={() => setStock(null)}
                  className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400`}
                >
                  변경
                </button>
              )}
            </div>
          ) : (
            <>
              <input
                id="trade-stock"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  search(e.target.value);
                }}
                placeholder="종목명 또는 티커 검색"
                autoComplete="off"
                className={`${INPUT_SM} w-full`}
              />
              {isSearching && (
                <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">검색 중...</p>
              )}
              {suggestions.length > 0 && (
                <ul className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 divide-y divide-gray-100 dark:divide-gray-700">
                  {suggestions.map((s) => (
                    <li key={`${s.ticker}-${s.market}`}>
                      <button
                        type="button"
                        onClick={() => {
                          setStock({ ticker: s.ticker, market: s.market, name: s.name });
                          setQuery("");
                          clearSuggestions();
                        }}
                        className={`${TOUCH_TARGET_ROW} w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800`}
                      >
                        {s.name}{" "}
                        <span className="text-xs text-gray-400 dark:text-gray-500">
                          {s.ticker} · {s.market}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="trade-qty" className={FORM_LABEL}>
              수량
            </label>
            <input
              id="trade-qty"
              type="number"
              inputMode="decimal"
              min="0"
              step="any"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              className={`${INPUT_SM} w-full`}
            />
          </div>
          <div>
            <label htmlFor="trade-price" className={FORM_LABEL}>
              단가 ({priceInUsd ? "USD" : "원"})
            </label>
            <input
              id="trade-price"
              type="number"
              inputMode="decimal"
              min="0"
              step="any"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              className={`${INPUT_SM} w-full`}
            />
            {priceInUsd && rate && price !== "" && (
              <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
                ≈ {fmtKrwPrice(convertUsdToKrw(Number(price), rate))} (현재 환율)
              </p>
            )}
          </div>
          <div>
            <label htmlFor="trade-date" className={FORM_LABEL}>
              거래일
            </label>
            <input
              id="trade-date"
              type="date"
              value={tradeDate}
              max={localToday()}
              onChange={(e) => setTradeDate(e.target.value)}
              className={`${INPUT_SM} w-full`}
            />
          </div>
          <div>
            <label htmlFor="trade-fee" className={FORM_LABEL}>
              수수료 (원, 선택)
            </label>
            <input
              id="trade-fee"
              type="number"
              inputMode="numeric"
              min="0"
              value={fee}
              onChange={(e) => setFee(e.target.value)}
              className={`${INPUT_SM} w-full`}
            />
          </div>
        </div>

        <div>
          <label htmlFor="trade-notes" className={FORM_LABEL}>
            메모 (선택)
          </label>
          <input
            id="trade-notes"
            value={notes}
            maxLength={500}
            onChange={(e) => setNotes(e.target.value)}
            className={`${INPUT_SM} w-full`}
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          {editing && (
            <button
              type="button"
              onClick={cancelEdit}
              className={`${TOUCH_TARGET_MIN} flex-1 px-5 py-2 rounded-lg text-sm font-medium border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300`}
            >
              수정 취소
            </button>
          )}
          <button
            type="submit"
            disabled={createMut.isPending || updateMut.isPending}
            className={`${TOUCH_TARGET_MIN} flex-1 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
          >
            {createMut.isPending || updateMut.isPending
              ? "저장 중..."
              : editing
                ? "기록 수정"
                : "기록 추가"}
          </button>
        </div>
      </form>

      {stock && records.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            이 종목의 기록
          </h3>
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {records.map((r) => (
              <li key={r.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0 text-sm">
                  <span
                    className={
                      r.side === "BUY"
                        ? "font-medium text-gray-900 dark:text-gray-50"
                        : "font-medium text-gray-500 dark:text-gray-400"
                    }
                  >
                    {r.side === "BUY" ? "매수" : "매도"}
                  </span>{" "}
                  <span className="text-gray-600 dark:text-gray-300">
                    {r.qty.toLocaleString()}주 × {fmtKrwPrice(r.price_krw)}
                  </span>
                  <p className="text-xs text-gray-400 dark:text-gray-500">{r.trade_date}</p>
                </div>
                <div className="flex items-center shrink-0">
                  <button
                    type="button"
                    onClick={() => startEdit(r)}
                    aria-label={`${r.trade_date} 기록 수정`}
                    aria-pressed={editing?.id === r.id}
                    className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors`}
                  >
                    <Pencil size={14} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (editing?.id === r.id) cancelEdit();
                      deleteMut.mutate(r.id);
                    }}
                    disabled={deleteMut.isPending}
                    aria-label={`${r.trade_date} 기록 삭제`}
                    className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors`}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}
