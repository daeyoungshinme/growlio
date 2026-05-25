import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { toast } from "../utils/toast";
import {
  fetchExchangeRateAlerts,
  createExchangeRateAlert,
  deleteExchangeRateAlert,
  type ExchangeRateAlert,
} from "../api/alerts";
import { fetchExchangeRate } from "../api/assets";

interface SettingsData {
  has_kis: boolean;
  has_dart: boolean;
  has_open_banking: boolean;
  ob_token_expires_at: string | null;
  goal_amount: number | null;
  goal_annual_return_pct: number | null;
  annual_deposit_goal: number | null;
  monthly_deposit_amount: number | null;
  retirement_target_year: number | null;
  user_email: string;
  notification_email: string | null;
}

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
  const [current, setCurrent] = useState<SettingsData | null>(null);
  const [dart, setDart] = useState({ api_key: "" });
  const [goal, setGoal] = useState({ goal_amount: "", goal_annual_return_pct: "", annual_deposit_goal: "", monthly_deposit_amount: "", retirement_target_year: "" });
  const [saving, setSaving] = useState<string | null>(null);

  // 목표환율 알림 상태
  const [alertForm, setAlertForm] = useState({ target_rate: "", direction: "BELOW" as "BELOW" | "ABOVE" });
  const [notificationEmail, setNotificationEmail] = useState("");

  const { data: alerts = [] } = useQuery<ExchangeRateAlert[]>({
    queryKey: ["exchange-rate-alerts"],
    queryFn: fetchExchangeRateAlerts,
  });

  const { data: exchangeRateData } = useQuery({
    queryKey: ["exchange-rate"],
    queryFn: fetchExchangeRate,
    refetchInterval: 60_000,
  });

  const createAlertMutation = useMutation({
    mutationFn: () => createExchangeRateAlert(Number(alertForm.target_rate), alertForm.direction),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exchange-rate-alerts"] });
      setAlertForm({ target_rate: "", direction: "BELOW" });
      toast("알림이 등록되었습니다", "success");
    },
    onError: () => {
      toast("알림 등록에 실패했습니다", "error");
    },
  });

  const deleteAlertMutation = useMutation({
    mutationFn: (id: string) => deleteExchangeRateAlert(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["exchange-rate-alerts"] }),
  });

  useEffect(() => {
    api.get<SettingsData>("/settings").then((r) => {
      setCurrent(r.data);
      if (r.data.goal_amount) setGoal((g) => ({ ...g, goal_amount: String(r.data.goal_amount) }));
      if (r.data.goal_annual_return_pct) setGoal((g) => ({ ...g, goal_annual_return_pct: String(r.data.goal_annual_return_pct) }));
      if (r.data.annual_deposit_goal) setGoal((g) => ({ ...g, annual_deposit_goal: String(r.data.annual_deposit_goal) }));
      if (r.data.monthly_deposit_amount) setGoal((g) => ({ ...g, monthly_deposit_amount: String(r.data.monthly_deposit_amount) }));
      if (r.data.retirement_target_year) setGoal((g) => ({ ...g, retirement_target_year: String(r.data.retirement_target_year) }));
      setNotificationEmail(r.data.notification_email ?? "");
    });
  }, []);

  const flash = (_key: string, ok: boolean, text: string) => {
    toast(text, ok ? "success" : "error");
  };

  const saveGoal = async () => {
    setSaving("goal");
    try {
      await api.put("/settings/goal", {
        goal_amount: goal.goal_amount ? Number(goal.goal_amount) : null,
        goal_annual_return_pct: goal.goal_annual_return_pct ? Number(goal.goal_annual_return_pct) : null,
        annual_deposit_goal: goal.annual_deposit_goal ? Number(goal.annual_deposit_goal) : null,
        monthly_deposit_amount: goal.monthly_deposit_amount ? Number(goal.monthly_deposit_amount) : null,
        retirement_target_year: goal.retirement_target_year ? Number(goal.retirement_target_year) : null,
      });
      flash("goal", true, "목표가 저장되었습니다");
    } catch {
      flash("goal", false, "저장에 실패했습니다");
    } finally {
      setSaving(null);
    }
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
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-50">설정</h1>

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
        {exchangeRateData && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            현재 환율: <span className="font-semibold text-gray-800 dark:text-gray-100">{exchangeRateData.usd_krw.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} 원</span>
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
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-500">목표환율 도달 시 이메일로 알림을 보내드립니다. 알림은 1회 발동 후 자동으로 비활성화됩니다.</p>
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
                <div className="text-sm">
                  <span className="font-medium text-gray-800 dark:text-gray-100">
                    {Number(alert.target_rate).toLocaleString("ko-KR")}원 {alert.direction === "BELOW" ? "이하" : "이상"}
                  </span>
                  {alert.is_active ? (
                    <span className="ml-2 text-xs text-green-600 dark:text-green-400">활성</span>
                  ) : (
                    <span className="ml-2 text-xs text-gray-400">
                      발동됨 {alert.triggered_at ? `(${new Date(alert.triggered_at).toLocaleDateString("ko-KR")})` : ""}
                    </span>
                  )}
                </div>
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
            ))}
          </div>
        )}
      </SectionCard>

      {/* 투자 목표 */}
      <SectionCard title="투자 목표 설정">
        <div>
          <label className={labelClass}>목표 자산 (원)</label>
          <input type="number" className={inputClass} value={goal.goal_amount}
            onChange={(e) => setGoal((g) => ({ ...g, goal_amount: e.target.value }))} placeholder="예: 100000000 (1억)" />
        </div>
        <div>
          <label className={labelClass}>목표 연 수익률 (%)</label>
          <input type="number" step="0.1" className={inputClass} value={goal.goal_annual_return_pct}
            onChange={(e) => setGoal((g) => ({ ...g, goal_annual_return_pct: e.target.value }))} placeholder="예: 7.0" />
        </div>
        <div>
          <label className={labelClass}>연간 입금 목표 (원)</label>
          <input type="number" className={inputClass} value={goal.annual_deposit_goal}
            onChange={(e) => setGoal((g) => ({ ...g, annual_deposit_goal: e.target.value }))}
            placeholder="예: 24000000 (월 200만원 × 12)" />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">올해 입출금 내역 기준으로 달성률이 대시보드에 표시됩니다</p>
        </div>
        <div>
          <label className={labelClass}>월 적립액 (원)</label>
          <input type="number" className={inputClass} value={goal.monthly_deposit_amount}
            onChange={(e) => setGoal((g) => ({ ...g, monthly_deposit_amount: e.target.value }))}
            placeholder="예: 500000 (50만원)" />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">투자 계획 페이지의 DCA 복리 시뮬레이션 기준 금액입니다</p>
        </div>
        <div>
          <label className={labelClass}>은퇴 목표시점 (연도)</label>
          <input type="number" className={inputClass} value={goal.retirement_target_year}
            onChange={(e) => setGoal((g) => ({ ...g, retirement_target_year: e.target.value }))}
            placeholder="예: 2045" min="2025" max="2100" />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">대시보드에 은퇴까지 남은 기간이 표시됩니다</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={saveGoal} disabled={saving === "goal"} className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors">
            {saving === "goal" ? "저장 중..." : "저장"}
          </button>
        </div>
      </SectionCard>
    </div>
  );
}
