import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sun, Moon, LogOut } from "lucide-react";
import { api } from "../api/client";
import { type SettingsData } from "../api/settings";
import { toast } from "../utils/toast";
import { useThemeStore } from "../stores/themeStore";
import { useAuthStore } from "../stores/authStore";
import {
  fetchExchangeRateAlerts,
  createExchangeRateAlert,
  reactivateExchangeRateAlert,
  deleteExchangeRateAlert,
  type ExchangeRateAlert,
} from "../api/alerts";
import { useExchangeRate } from "../hooks/useExchangeRate";
import { invalidateAlertData } from "../utils/queryInvalidation";
import { QUERY_KEYS } from "../constants/queryKeys";

function SectionCard({ title, badge, children }: { title: string; badge?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">{title}</h2>
        {badge}
      </div>
      {children}
    </div>
  );
}

function ConnectedBadge() {
  return <span className="text-xs bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full font-medium">연결됨</span>;
}

const inputClass = "mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
const labelClass = "text-sm font-medium text-gray-700 dark:text-gray-300";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { isDark, toggle } = useThemeStore();
  const { logout } = useAuthStore();
  const [current, setCurrent] = useState<SettingsData | null>(null);
  const [dart, setDart] = useState({ api_key: "" });
  const [saving, setSaving] = useState<string | null>(null);

  // 목표환율 알림 상태
  const [alertForm, setAlertForm] = useState({ target_rate: "", direction: "BELOW" as "BELOW" | "ABOVE", max_trigger_count: "1" });
  const [notificationEmail, setNotificationEmail] = useState("");

  const { data: alerts = [] } = useQuery<ExchangeRateAlert[]>({
    queryKey: QUERY_KEYS.exchangeRateAlerts,
    queryFn: fetchExchangeRateAlerts,
  });

  const usdKrw = useExchangeRate();

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
    onError: () => {
      toast("알림 등록에 실패했습니다", "error");
    },
  });

  const reactivateAlertMutation = useMutation({
    mutationFn: (id: string) => reactivateExchangeRateAlert(id),
    onSuccess: () => {
      invalidateAlertData(queryClient);
      toast("알림이 재활성화되었습니다", "success");
    },
    onError: () => {
      toast("재활성화에 실패했습니다", "error");
    },
  });

  const deleteAlertMutation = useMutation({
    mutationFn: (id: string) => deleteExchangeRateAlert(id),
    onSuccess: () => invalidateAlertData(queryClient),
  });

  useEffect(() => {
    api.get<SettingsData>("/settings").then((r) => {
      setCurrent(r.data);
      setNotificationEmail(r.data.notification_email ?? "");
    });
  }, []);

  const flash = (_key: string, ok: boolean, text: string) => {
    toast(text, ok ? "success" : "error");
  };

  const saveDart = async () => {
    setSaving("dart");
    try {
      await api.put("/settings/dart", { api_key: dart.api_key });
      flash("dart", true, "DART API 키가 저장되었습니다");
      const r = await api.get<SettingsData>("/settings");
      setCurrent(r.data);
    } catch {
      flash("dart", false, "저장에 실패했습니다");
    } finally {
      setSaving(null);
    }
  };

  const deleteDart = async () => {
    await api.delete("/settings/dart");
    flash("dart", true, "DART API 키가 삭제되었습니다");
    const r = await api.get<SettingsData>("/settings");
    setCurrent(r.data);
  };

  const saveNotificationEmail = async () => {
    setSaving("notification-email");
    try {
      await api.put("/settings/notification-email", { notification_email: notificationEmail || null });
      flash("notification-email", true, "알림 이메일이 저장되었습니다");
      const r = await api.get<SettingsData>("/settings");
      setCurrent(r.data);
    } catch {
      flash("notification-email", false, "저장에 실패했습니다");
    } finally {
      setSaving(null);
    }
  };

  const sendTestEmail = async () => {
    setSaving("test-email");
    try {
      await api.post("/settings/test-email");
      flash("test-email", true, "테스트 이메일을 발송했습니다. 받은편지함을 확인하세요.");
    } catch {
      flash("test-email", false, "이메일 발송에 실패했습니다. SMTP 설정을 확인하세요.");
    } finally {
      setSaving(null);
    }
  };

  const connectOpenBanking = async () => {
    const r = await api.get<{ authorize_url: string }>("/open-banking/connect");
    window.location.href = r.data.authorize_url;
  };

  const disconnectOpenBanking = async () => {
    await api.delete("/open-banking/disconnect");
    const r = await api.get<SettingsData>("/settings");
    setCurrent(r.data);
    flash("ob", true, "오픈뱅킹 연결이 해제되었습니다");
  };

  return (
    <div className="space-y-6 max-w-xl">
      {/* DART OpenAPI */}
      <SectionCard title="DART OpenAPI (금융감독원)" badge={current?.has_dart ? <ConnectedBadge /> : undefined}>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          opendart.fss.or.kr에서 발급받은 API 키를 입력하세요. 국내 주식 배당 데이터 조회에 사용됩니다.
        </p>
        <div>
          <label className={labelClass}>API Key</label>
          <input
            type="password"
            className={inputClass}
            value={dart.api_key}
            onChange={(e) => setDart({ api_key: e.target.value })}
            placeholder={current?.has_dart ? "••••••••" : "DART OpenAPI 인증키"}
          />
        </div>
        <div className="flex items-center gap-3">
          <button onClick={saveDart} disabled={saving === "dart"} className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {saving === "dart" ? "저장 중..." : "저장"}
          </button>
          {current?.has_dart && (
            <button onClick={deleteDart} className="px-5 py-2 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 transition-colors">
              삭제
            </button>
          )}
        </div>
      </SectionCard>

      {/* 오픈뱅킹 */}
      <SectionCard title="금융결제원 오픈뱅킹" badge={current?.has_open_banking ? <ConnectedBadge /> : undefined}>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          오픈뱅킹을 연결하면 은행 통장 잔액을 자동으로 불러올 수 있습니다.
          {current?.ob_token_expires_at && (
            <> 토큰 만료: {new Date(current.ob_token_expires_at).toLocaleDateString("ko-KR")}</>
          )}
        </p>
        <div className="flex items-center gap-3">
          {current?.has_open_banking ? (
            <button onClick={disconnectOpenBanking} className="px-5 py-2 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 transition-colors">
              연결 해제
            </button>
          ) : (
            <button onClick={connectOpenBanking} className="bg-green-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition-colors">
              오픈뱅킹 연결
            </button>
          )}
        </div>
      </SectionCard>

      {/* 목표환율 알림 */}
      <SectionCard title="목표환율 알림 (USD/KRW)">
        {usdKrw !== null && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            현재 환율: <span className="font-semibold text-gray-800 dark:text-gray-100">{usdKrw.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원</span>
          </p>
        )}
        <div>
          <label className={labelClass}>알림 수신 이메일</label>
          <input
            type="email"
            className={inputClass}
            value={notificationEmail}
            onChange={(e) => setNotificationEmail(e.target.value)}
            placeholder={current?.user_email ?? "이메일 주소"}
          />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
            비워두면 로그인 이메일({current?.user_email})로 발송됩니다.
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
        <p className="text-xs text-gray-400 dark:text-gray-500">목표환율 도달 시 이메일로 알림을 보내드립니다. 다회 발동 알림은 발동 간 최소 1시간 간격이 적용됩니다.</p>
        <div className="flex gap-2 flex-wrap">
          <div className="flex-1 min-w-[120px]">
            <label className={labelClass}>목표환율 (원)</label>
            <input
              type="number"
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
                    {Number(alert.target_rate).toLocaleString("ko-KR")}원 {alert.direction === "BELOW" ? "이하" : "이상"}
                  </span>
                  <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">
                    {alert.trigger_count}/{alert.max_trigger_count}회
                  </span>
                  {alert.is_active ? (
                    <span className="ml-2 text-xs text-green-600 dark:text-green-400">활성</span>
                  ) : (
                    <span className="ml-2 text-xs text-gray-400">
                      비활성 {alert.triggered_at ? `(${new Date(alert.triggered_at).toLocaleDateString("ko-KR")})` : ""}
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
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      {/* 투자 목표 */}
      <SectionCard title="투자 목표 설정">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          월 적립액, 목표 금액, 연간 입금 목표 등 투자 목표는 투자계획 페이지에서 통합 설정합니다.
        </p>
        <Link
          to="/invest-plan"
          state={{ openEdit: true }}
          className="inline-flex items-center gap-2 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          투자계획 설정하기 →
        </Link>
      </SectionCard>

      {/* 모바일 전용: 앱 설정 (데스크톱은 사이드바에서 접근) */}
      <div className="lg:hidden">
        <SectionCard title="앱 설정">
          <button
            onClick={toggle}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
            {isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
          </button>
          <button
            onClick={logout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
          >
            <LogOut size={18} />
            로그아웃
          </button>
        </SectionCard>
      </div>
    </div>
  );
}
