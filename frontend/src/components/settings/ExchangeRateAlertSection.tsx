import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import {
  fetchExchangeRateAlerts,
  createExchangeRateAlert,
  reactivateExchangeRateAlert,
  deleteExchangeRateAlert,
  type ExchangeRateAlert,
} from "@/api/alerts";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { invalidateAlertData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { SectionCard, inputClass, labelClass } from "./shared";

interface Props {
  userEmail?: string;
  onSettingsChange: () => void;
}

const DeleteIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

export function ExchangeRateAlertSection({ userEmail, onSettingsChange }: Props) {
  const queryClient = useQueryClient();
  const usdKrw = useExchangeRate();

  const [alertForm, setAlertForm] = useState({
    target_rate: "",
    direction: "BELOW" as "BELOW" | "ABOVE",
    max_trigger_count: "1",
  });
  const [notificationEmail, setNotificationEmail] = useState(userEmail ?? "");
  const [saving, setSaving] = useState<string | null>(null);

  const { data: alerts = [] } = useQuery<ExchangeRateAlert[]>({
    queryKey: QUERY_KEYS.exchangeRateAlerts,
    queryFn: fetchExchangeRateAlerts,
  });

  const createAlertMutation = useMutation({
    mutationFn: () =>
      createExchangeRateAlert(
        Number(alertForm.target_rate),
        alertForm.direction,
        Math.max(1, Number(alertForm.max_trigger_count) || 1),
      ),
    onSuccess: () => {
      invalidateAlertData(queryClient);
      setAlertForm({ target_rate: "", direction: "BELOW", max_trigger_count: "1" });
      toast("알림이 등록되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "알림 등록에 실패했습니다"), "error"),
  });

  const reactivateAlertMutation = useMutation({
    mutationFn: (id: string) => reactivateExchangeRateAlert(id),
    onSuccess: () => {
      invalidateAlertData(queryClient);
      toast("알림이 재활성화되었습니다", "success");
    },
    onError: (e) => toast(extractErrorMessage(e, "재활성화에 실패했습니다"), "error"),
  });

  const deleteAlertMutation = useMutation({
    mutationFn: (id: string) => deleteExchangeRateAlert(id),
    onSuccess: () => invalidateAlertData(queryClient),
  });

  const saveNotificationEmail = async () => {
    setSaving("notification-email");
    try {
      await api.put("/settings/notification-email", { notification_email: notificationEmail || null });
      toast("알림 이메일이 저장되었습니다", "success");
      onSettingsChange();
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(null);
    }
  };

  const sendTestEmail = async () => {
    setSaving("test-email");
    try {
      await api.post("/settings/test-email");
      toast("테스트 이메일을 발송했습니다. 받은편지함을 확인하세요.", "success");
    } catch {
      toast("이메일 발송에 실패했습니다. SMTP 설정을 확인하세요.", "error");
    } finally {
      setSaving(null);
    }
  };

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
      <div>
        <label className={labelClass}>알림 수신 이메일</label>
        <input
          type="email"
          className={inputClass}
          value={notificationEmail}
          onChange={(e) => setNotificationEmail(e.target.value)}
          placeholder={userEmail ?? "이메일 주소"}
        />
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          비워두면 로그인 이메일({userEmail})로 발송됩니다.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={saveNotificationEmail}
          disabled={saving === "notification-email"}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving === "notification-email" ? "저장 중..." : "저장"}
        </button>
        <button
          onClick={sendTestEmail}
          disabled={saving === "test-email"}
          className="px-5 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          {saving === "test-email" ? "발송 중..." : "테스트 발송"}
        </button>
      </div>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        목표환율 도달 시 이메일로 알림을 보내드립니다. 다회 발동 알림은 발동 간 최소 1시간 간격이 적용됩니다.
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
            onChange={(e) => setAlertForm((f) => ({ ...f, direction: e.target.value as "BELOW" | "ABOVE" }))}
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
                  className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
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
