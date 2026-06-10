import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchStockPriceAlerts,
  createStockPriceAlert,
  reactivateStockPriceAlert,
  deleteStockPriceAlert,
  type StockPriceAlert,
} from "@/api/alerts";
import type { StockSuggestion } from "@/api/assets";
import { useStockSearch } from "@/hooks/useStockSearch";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { invalidateStockPriceAlertData } from "@/utils/queryInvalidation";
import { SectionCard, inputClass, labelClass } from "./shared";

const DeleteIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

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

  const { data: stockAlerts = [] } = useQuery<StockPriceAlert[]>({
    queryKey: QUERY_KEYS.stockPriceAlerts,
    queryFn: fetchStockPriceAlerts,
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!selectedStock || !form.target_price) throw new Error("입력값 없음");
      return createStockPriceAlert({
        ticker: selectedStock.ticker,
        market: selectedStock.market,
        name: selectedStock.name,
        target_price: Number(form.target_price),
        direction: form.direction,
        max_trigger_count: Math.max(1, Number(form.max_trigger_count) || 1),
      });
    },
    onSuccess: () => {
      invalidateStockPriceAlertData(qc);
      setForm({ query: "", target_price: "", direction: "BELOW", max_trigger_count: "1" });
      setSelectedStock(null);
      clearSuggestions();
      toast("주가 알림이 등록되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error"),
  });

  const reactivateMutation = useMutation({
    mutationFn: (id: string) => reactivateStockPriceAlert(id),
    onSuccess: () => { invalidateStockPriceAlertData(qc); toast("알림이 재활성화되었습니다", "success"); },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteStockPriceAlert(id),
    onSuccess: () => invalidateStockPriceAlertData(qc),
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
          <label className={labelClass}>종목 검색</label>
          <input
            type="text"
            className={inputClass}
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
                  className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                  onClick={() => {
                    setSelectedStock(s);
                    setForm((f) => ({ ...f, query: `${s.name} (${s.ticker})` }));
                    clearSuggestions();
                  }}
                >
                  <span className="font-medium text-gray-800 dark:text-gray-200">{s.name}</span>
                  <span className="ml-2 text-xs text-gray-400">{s.ticker} · {s.market}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <div className="flex-1 min-w-[120px]">
            <label className={labelClass}>목표가 (원)</label>
            <input
              type="number"
              className={inputClass}
              value={form.target_price}
              onChange={(e) => setForm((f) => ({ ...f, target_price: e.target.value }))}
              placeholder="예: 30000"
              min="0"
            />
          </div>
          <div className="flex-1 min-w-[100px]">
            <label className={labelClass}>조건</label>
            <select
              className={inputClass}
              value={form.direction}
              onChange={(e) => setForm((f) => ({ ...f, direction: e.target.value as "BELOW" | "ABOVE" }))}
            >
              <option value="BELOW">이하 (↓)</option>
              <option value="ABOVE">이상 (↑)</option>
            </select>
          </div>
          <div className="flex-1 min-w-[80px]">
            <label className={labelClass}>알림 횟수</label>
            <input
              type="number"
              className={inputClass}
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
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
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
                  {Number(alert.target_price).toLocaleString("ko-KR")}원{" "}
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
              </div>
              <div className="flex items-center gap-1 ml-2 shrink-0">
                {!alert.is_active && (
                  <button
                    onClick={() => reactivateMutation.mutate(alert.id)}
                    disabled={reactivateMutation.isPending}
                    className="px-2 py-1 text-xs text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-600 rounded-md hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
                  >
                    재활성화
                  </button>
                )}
                <button
                  onClick={() => deleteMutation.mutate(alert.id)}
                  disabled={deleteMutation.isPending}
                  className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
                >
                  <DeleteIcon />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}
