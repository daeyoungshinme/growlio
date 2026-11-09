import { useId, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchStockPriceAlerts,
  createStockPriceAlert,
  reactivateStockPriceAlert,
  deleteStockPriceAlert,
  type StockPriceAlert,
} from "@/api/alerts";
import type { StockSuggestion } from "@/api/assets";
import { useStockSearch } from "@/hooks/useStockSearch";
import { useAlertCrud } from "@/hooks/useAlertCrud";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { isOverseasMarket } from "@/constants/markets";
import { convertUsdToKrw, fmtKrwPrice } from "@/utils/format";
import {
  TOUCH_HEIGHT_MIN,
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
  TOUCH_TARGET_MIN,
  TOUCH_TARGET_MIN_MOBILE_ONLY,
} from "@/constants/uiSizes";
import ConfirmModal from "@/components/common/ConfirmModal";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { invalidateStockPriceAlertData } from "@/utils/queryInvalidation";
import { SectionCard, DeleteIcon } from "./shared";
import { FORM_INPUT_SM, LABEL_MD } from "@/constants/inputStyles";

export function StockPriceAlertSection() {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    query: "",
    target_price: "",
    direction: "BELOW" as "BELOW" | "ABOVE",
    max_trigger_count: "1",
  });
  const { suggestions, isSearching, search: runSearch, clearSuggestions } = useStockSearch();
  const [selectedStock, setSelectedStock] = useState<StockSuggestion | null>(null);
  const rate = useExchangeRate();
  const idBase = useId();
  const fieldId = (name: string) => `${idBase}-${name}`;
  // 백엔드는 목표가를 원화로 비교한다 — 해외 종목은 달러로 받아 현재 환율로 환산해 보낸다(plans/118 C6).
  // 예전엔 "목표가 (원)"에 SCHD 27을 넣으면 27원으로 저장돼 이상(↑) 알림이 즉시, 이하(↓)는 영영 울리지 않았다.
  const inUsd = selectedStock ? isOverseasMarket(selectedStock.market) : false;
  // 목표가를 입력한 시점의 단위 — 종목을 다시 고를 때 단위가 바뀌었는지 판단한다
  const targetTypedInUsd = useRef(false);
  const targetKrw = inUsd
    ? convertUsdToKrw(Number(form.target_price), rate)
    : Number(form.target_price);

  const [pendingDelete, setPendingDelete] = useState<StockPriceAlert | null>(null);
  const {
    items: stockAlerts,
    reactivateMutation,
    deleteMutation,
  } = useAlertCrud<StockPriceAlert>({
    queryKey: QUERY_KEYS.stockPriceAlerts,
    queryFn: fetchStockPriceAlerts,
    reactivateFn: reactivateStockPriceAlert,
    deleteFn: deleteStockPriceAlert,
    invalidateFn: invalidateStockPriceAlertData,
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!selectedStock || !form.target_price) throw new Error("입력값 없음");
      if (inUsd && !rate) {
        throw new Error("환율 정보를 불러오지 못해 달러 목표가를 원화로 환산할 수 없습니다");
      }
      return createStockPriceAlert({
        ticker: selectedStock.ticker,
        market: selectedStock.market,
        name: selectedStock.name,
        target_price: targetKrw,
        direction: form.direction,
        max_trigger_count: Math.max(1, Number(form.max_trigger_count) || 1),
      });
    },
    onSuccess: () => {
      void invalidateStockPriceAlertData(qc);
      setForm({ query: "", target_price: "", direction: "BELOW", max_trigger_count: "1" });
      setSelectedStock(null);
      clearSuggestions();
      toast("주가 알림이 등록되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error"),
  });

  const handleSearch = (value: string) => {
    setForm((f) => ({ ...f, query: value }));
    setSelectedStock(null);
    runSearch(value);
  };

  return (
    <SectionCard title="주가 목표 알림">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        특정 종목이 목표가에 도달하면 이메일로 알림을 보내드립니다.
      </p>
      <div className="space-y-3">
        <div className="relative">
          <label htmlFor={fieldId("query")} className={LABEL_MD}>
            종목 검색
          </label>
          <input
            id={fieldId("query")}
            type="text"
            className={FORM_INPUT_SM}
            value={form.query}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="종목명 또는 티커 (예: SCHD, 삼성전자)"
          />
          {selectedStock && (
            <div className="mt-1 text-xs text-green-600 dark:text-green-400 font-medium">
              선택됨: {selectedStock.name} ({selectedStock.ticker} · {selectedStock.market})
            </div>
          )}
          {isSearching && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">검색 중...</p>
          )}
          {suggestions.length > 0 && !selectedStock && (
            <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
              {suggestions.map((s) => (
                <button
                  key={`${s.ticker}-${s.market}`}
                  className={`w-full text-left px-3 ${TOUCH_HEIGHT_MIN} text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors`}
                  onClick={() => {
                    setSelectedStock(s);
                    // 입력할 때와 단위(원↔달러)가 달라지면 숫자를 지운다 — 30000(원)이 $30,000으로,
                    // 27(달러)이 27원으로 바뀌어 저장되지 않게(plans/119 C2)
                    const unitChanged = isOverseasMarket(s.market) !== targetTypedInUsd.current;
                    setForm((f) => ({
                      ...f,
                      query: `${s.name} (${s.ticker})`,
                      target_price: unitChanged ? "" : f.target_price,
                    }));
                    clearSuggestions();
                  }}
                >
                  <span className="font-medium text-gray-800 dark:text-gray-200">{s.name}</span>
                  <span className="ml-2 text-xs text-gray-400">
                    {s.ticker} · {s.market}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          <div className="col-span-2 sm:col-span-1">
            <label htmlFor={fieldId("target")} className={LABEL_MD}>
              {inUsd ? "목표가 (USD)" : "목표가 (원)"}
            </label>
            <input
              id={fieldId("target")}
              type="number"
              inputMode="decimal"
              className={FORM_INPUT_SM}
              value={form.target_price}
              onChange={(e) => {
                targetTypedInUsd.current = inUsd;
                setForm((f) => ({ ...f, target_price: e.target.value }));
              }}
              placeholder={inUsd ? "예: 27.5" : "예: 30000"}
              min="0"
              step={inUsd ? "0.01" : undefined}
            />
            {inUsd && rate && form.target_price !== "" && (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                ≈ {fmtKrwPrice(targetKrw)} (현재 환율로 저장)
              </p>
            )}
          </div>
          <div>
            <label htmlFor={fieldId("direction")} className={LABEL_MD}>
              조건
            </label>
            <select
              id={fieldId("direction")}
              className={FORM_INPUT_SM}
              value={form.direction}
              onChange={(e) =>
                setForm((f) => ({ ...f, direction: e.target.value as "BELOW" | "ABOVE" }))
              }
            >
              <option value="BELOW">이하 (↓)</option>
              <option value="ABOVE">이상 (↑)</option>
            </select>
          </div>
          <div>
            <label htmlFor={fieldId("count")} className={LABEL_MD}>
              알림 횟수
            </label>
            <input
              id={fieldId("count")}
              type="number"
              inputMode="numeric"
              className={FORM_INPUT_SM}
              value={form.max_trigger_count}
              onChange={(e) => setForm((f) => ({ ...f, max_trigger_count: e.target.value }))}
              min="1"
              placeholder="1"
            />
          </div>
        </div>
        <button
          onClick={() => createMutation.mutate()}
          disabled={!selectedStock || !form.target_price || createMutation.isPending}
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} bg-blue-600 text-white px-5 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors`}
        >
          {createMutation.isPending ? "등록 중..." : "알림 추가"}
        </button>
      </div>
      {stockAlerts.length > 0 && (
        <div className="mt-2 space-y-2">
          {stockAlerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center justify-between px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
            >
              <div className="text-sm min-w-0">
                <span className="font-medium text-gray-800 dark:text-gray-100">
                  {alert.name} ({alert.ticker})
                </span>
                <span className="ml-2 text-xs text-gray-400">
                  {fmtKrwPrice(Number(alert.target_price))}{" "}
                  {alert.direction === "BELOW" ? "이하" : "이상"}
                </span>
                <span className="ml-2 text-xs text-gray-400">
                  {alert.trigger_count}/{alert.max_trigger_count}회
                </span>
                {alert.is_active ? (
                  <span className="ml-2 text-xs text-green-600 dark:text-green-400">활성</span>
                ) : (
                  <span className="ml-2 text-xs text-gray-400">비활성</span>
                )}
                {alert.needs_reentry && (
                  <p className="mt-0.5 text-xs text-amber-600 dark:text-amber-400">
                    다시 입력 필요 — 달러 목표가가 원화로 저장돼 알림이 울리지 않아요. 삭제 후
                    달러로 다시 등록해 주세요.
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1 ml-2 shrink-0">
                {!alert.is_active && (
                  <button
                    onClick={() => reactivateMutation.mutate(alert.id)}
                    disabled={reactivateMutation.isPending}
                    className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-600 rounded-md hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors`}
                  >
                    재활성화
                  </button>
                )}
                <button
                  onClick={() => setPendingDelete(alert)}
                  disabled={deleteMutation.isPending}
                  className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors`}
                  aria-label={`${alert.name} 주가 알림 삭제`}
                >
                  <DeleteIcon />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {pendingDelete && (
        <ConfirmModal
          message={`${pendingDelete.name} ${fmtKrwPrice(Number(pendingDelete.target_price))} ${pendingDelete.direction === "BELOW" ? "이하" : "이상"} 알림을 삭제할까요?`}
          confirmLabel="삭제"
          onConfirm={() => {
            deleteMutation.mutate(pendingDelete.id);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </SectionCard>
  );
}
