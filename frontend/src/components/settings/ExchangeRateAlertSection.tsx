import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchExchangeRateAlerts,
  createExchangeRateAlert,
  reactivateExchangeRateAlert,
  deleteExchangeRateAlert,
  type ExchangeRateAlert,
} from "@/api/alerts";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { useAlertCrud } from "@/hooks/useAlertCrud";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";
import { invalidateAlertData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { SectionCard, DeleteIcon, inputClass, labelClass } from "./shared";

export function ExchangeRateAlertSection() {
  const queryClient = useQueryClient();
  const usdKrw = useExchangeRate();

  const [alertForm, setAlertForm] = useState({
    target_rate: "",
    direction: "BELOW" as "BELOW" | "ABOVE",
    max_trigger_count: "1",
  });

  const {
    items: alerts,
    reactivateMutation: reactivateAlertMutation,
    deleteMutation: deleteAlertMutation,
  } = useAlertCrud<ExchangeRateAlert>({
    queryKey: QUERY_KEYS.exchangeRateAlerts,
    queryFn: fetchExchangeRateAlerts,
    reactivateFn: reactivateExchangeRateAlert,
    deleteFn: deleteExchangeRateAlert,
    invalidateFn: invalidateAlertData,
  });

  const createAlertMutation = useMutation({
    mutationFn: () =>
      createExchangeRateAlert(
        Number(alertForm.target_rate),
        alertForm.direction,
        Math.max(1, Number(alertForm.max_trigger_count) || 1),
      ),
    onSuccess: () => {
      void invalidateAlertData(queryClient);
      setAlertForm({ target_rate: "", direction: "BELOW", max_trigger_count: "1" });
      toast("알림이 등록되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error"),
  });

  return (
    <SectionCard title="목표환율 알림 (USD/KRW)">
      {usdKrw !== null && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          현재 환율:{" "}
          <span className="font-semibold text-gray-800 dark:text-gray-100">
            {usdKrw.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원
          </span>
        </p>
      )}
      <p className="text-xs text-gray-400 dark:text-gray-500">
        목표환율 도달 시 이메일로 알림을 보내드립니다. 다회 발동 알림은 발동 간 최소 1시간 간격이
        적용됩니다.
      </p>
      <div className="flex gap-2 flex-wrap">
        <div className="flex-1 min-w-[120px]">
          <label className={labelClass}>목표환율 (원)</label>
          <input
            type="number"
            inputMode="decimal"
            className={inputClass}
            value={alertForm.target_rate}
            onChange={(e) => setAlertForm((f) => ({ ...f, target_rate: e.target.value }))}
            placeholder="예: 1300"
            min="0"
          />
        </div>
        <div className="flex-1 min-w-[100px]">
          <label className={labelClass}>조건</label>
          <select
            className={inputClass}
            value={alertForm.direction}
            onChange={(e) =>
              setAlertForm((f) => ({ ...f, direction: e.target.value as "BELOW" | "ABOVE" }))
            }
          >
            <option value="BELOW">이하 (↓)</option>
            <option value="ABOVE">이상 (↑)</option>
          </select>
        </div>
        <div className="flex-1 min-w-[80px]">
          <label className={labelClass}>알림 횟수</label>
          <input
            type="number"
            inputMode="numeric"
            className={inputClass}
            value={alertForm.max_trigger_count}
            onChange={(e) => setAlertForm((f) => ({ ...f, max_trigger_count: e.target.value }))}
            min="1"
            placeholder="1"
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => createAlertMutation.mutate()}
          disabled={!alertForm.target_rate || createAlertMutation.isPending}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {createAlertMutation.isPending ? "등록 중..." : "알림 추가"}
        </button>
      </div>
      {alerts.length > 0 && (
        <div className="mt-2 space-y-2">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center justify-between px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
            >
              <div className="text-sm min-w-0">
                <span className="font-medium text-gray-800 dark:text-gray-100">
                  {Number(alert.target_rate).toLocaleString("ko-KR")}원{" "}
                  {alert.direction === "BELOW" ? "이하" : "이상"}
                </span>
                <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                  {alert.trigger_count}/{alert.max_trigger_count}회
                </span>
                {alert.is_active ? (
                  <span className="ml-2 text-xs text-green-600 dark:text-green-400">활성</span>
                ) : (
                  <span className="ml-2 text-xs text-gray-400">
                    비활성{" "}
                    {alert.triggered_at
                      ? `(${new Date(alert.triggered_at).toLocaleDateString("ko-KR")})`
                      : ""}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 ml-2 shrink-0">
                {!alert.is_active && (
                  <button
                    onClick={() => reactivateAlertMutation.mutate(alert.id)}
                    disabled={reactivateAlertMutation.isPending}
                    className="px-2 py-1 text-xs text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-600 rounded-md hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
                    title="재활성화"
                  >
                    재활성화
                  </button>
                )}
                <button
                  onClick={() => deleteAlertMutation.mutate(alert.id)}
                  disabled={deleteAlertMutation.isPending}
                  className={`${TOUCH_TARGET_MIN} p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors`}
                  title="삭제"
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
