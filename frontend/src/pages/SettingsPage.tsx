import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Sun, Moon, LogOut } from "lucide-react";
import { api } from "../api/client";
import { type SettingsData, updateAutoDca } from "../api/settings";
import { fetchAccounts } from "../api/assets";
import { fetchPortfolios } from "../api/portfolios";
import { toast } from "../utils/toast";
import { useThemeStore } from "../stores/themeStore";
import { useAuthStore } from "../stores/authStore";
import {
  fetchExchangeRateAlerts,
  createExchangeRateAlert,
  reactivateExchangeRateAlert,
  deleteExchangeRateAlert,
  fetchStockPriceAlerts,
  createStockPriceAlert,
  reactivateStockPriceAlert,
  deleteStockPriceAlert,
  type ExchangeRateAlert,
  type StockPriceAlert,
} from "../api/alerts";
import { searchStocks, type StockSuggestion } from "../api/assets";
import { useExchangeRate } from "../hooks/useExchangeRate";
import { invalidateAlertData } from "../utils/queryInvalidation";
import { QUERY_KEYS } from "../constants/queryKeys";
import { STALE_TIME } from "../constants/queryConfig";

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

  const { data: portfolios = [] } = useQuery({
    queryKey: QUERY_KEYS.portfolios,
    queryFn: fetchPortfolios,
    staleTime: STALE_TIME.MEDIUM,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
  });

  const kisAccounts = accounts.filter((a) => a.asset_type === "STOCK_KIS" && a.is_active);

  const [dcaForm, setDcaForm] = useState({
    enabled: false,
    day: "1",
    amount: "",
    portfolio_id: "",
    account_id: "",
  });

  const saveDcaMutation = useMutation({
    mutationFn: () =>
      updateAutoDca({
        enabled: dcaForm.enabled,
        day: dcaForm.day ? Number(dcaForm.day) : null,
        amount: dcaForm.amount ? Number(dcaForm.amount) : null,
        portfolio_id: dcaForm.portfolio_id || null,
        account_id: dcaForm.account_id || null,
      }),
    onSuccess: () => {
      toast("자동 정기매수 설정이 저장되었습니다", "success");
      api.get<SettingsData>("/settings").then((r) => {
        setCurrent(r.data);
        syncDcaForm(r.data);
      });
    },
    onError: () => toast("저장에 실패했습니다", "error"),
  });

  const syncDcaForm = (data: SettingsData) => {
    setDcaForm({
      enabled: data.auto_dca_enabled,
      day: data.auto_dca_day ? String(data.auto_dca_day) : "1",
      amount: data.auto_dca_amount ? String(data.auto_dca_amount) : "",
      portfolio_id: data.auto_dca_portfolio_id ?? "",
      account_id: data.auto_dca_account_id ?? "",
    });
  };

  const usdKrw = useExchangeRate();

  // 주가 목표 알림 상태
  const { data: stockAlerts = [], refetch: refetchStockAlerts } = useQuery<StockPriceAlert[]>({
    queryKey: QUERY_KEYS.stockPriceAlerts,
    queryFn: fetchStockPriceAlerts,
  });

  const [stockAlertForm, setStockAlertForm] = useState({
    query: "",
    target_price: "",
    direction: "BELOW" as "BELOW" | "ABOVE",
    max_trigger_count: "1",
  });
  const [stockSuggestions, setStockSuggestions] = useState<StockSuggestion[]>([]);
  const [selectedStock, setSelectedStock] = useState<StockSuggestion | null>(null);
  const [stockSearchLoading, setStockSearchLoading] = useState(false);
  const stockSearchTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const handleStockSearch = (value: string) => {
    setStockAlertForm((f) => ({ ...f, query: value }));
    setSelectedStock(null);
    if (stockSearchTimer.current !== undefined) clearTimeout(stockSearchTimer.current);
    if (!value.trim()) { setStockSuggestions([]); return; }
    stockSearchTimer.current = setTimeout(async () => {
      setStockSearchLoading(true);
      try { setStockSuggestions(await searchStocks(value.trim())); }
      catch { setStockSuggestions([]); }
      finally { setStockSearchLoading(false); }
    }, 300);
  };

  const createStockAlertMutation = useMutation({
    mutationFn: () => {
      if (!selectedStock || !stockAlertForm.target_price) throw new Error("입력값 없음");
      return createStockPriceAlert({
        ticker: selectedStock.ticker,
        market: selectedStock.market,
        name: selectedStock.name,
        target_price: Number(stockAlertForm.target_price),
        direction: stockAlertForm.direction,
        max_trigger_count: Math.max(1, Number(stockAlertForm.max_trigger_count) || 1),
      });
    },
    onSuccess: () => {
      refetchStockAlerts();
      setStockAlertForm({ query: "", target_price: "", direction: "BELOW", max_trigger_count: "1" });
      setSelectedStock(null);
      setStockSuggestions([]);
      toast("주가 알림이 등록되었습니다", "success");
    },
    onError: () => toast("알림 등록에 실패했습니다", "error"),
  });

  const reactivateStockAlertMutation = useMutation({
    mutationFn: (id: string) => reactivateStockPriceAlert(id),
    onSuccess: () => { refetchStockAlerts(); toast("알림이 재활성화되었습니다", "success"); },
  });

  const deleteStockAlertMutation = useMutation({
    mutationFn: (id: string) => deleteStockPriceAlert(id),
    onSuccess: () => refetchStockAlerts(),
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
      syncDcaForm(r.data);
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

      {/* 주가 목표 알림 */}
      <SectionCard title="주가 목표 알림">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          특정 종목이 목표가에 도달하면 이메일로 알림을 보내드립니다.
        </p>
        <div className="space-y-3">
          {/* 종목 검색 */}
          <div className="relative">
            <label className={labelClass}>종목 검색</label>
            <input
              type="text"
              className={inputClass}
              value={stockAlertForm.query}
              onChange={(e) => handleStockSearch(e.target.value)}
              placeholder="종목명 또는 티커 (예: SCHD, 삼성전자)"
            />
            {selectedStock && (
              <div className="mt-1 text-xs text-green-600 dark:text-green-400 font-medium">
                선택됨: {selectedStock.name} ({selectedStock.ticker} · {selectedStock.market})
              </div>
            )}
            {stockSearchLoading && (
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">검색 중...</p>
            )}
            {stockSuggestions.length > 0 && !selectedStock && (
              <div className="absolute z-10 w-full mt-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg max-h-48 overflow-y-auto">
                {stockSuggestions.map((s) => (
                  <button
                    key={`${s.ticker}-${s.market}`}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    onClick={() => {
                      setSelectedStock(s);
                      setStockAlertForm((f) => ({ ...f, query: `${s.name} (${s.ticker})` }));
                      setStockSuggestions([]);
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
                value={stockAlertForm.target_price}
                onChange={(e) => setStockAlertForm((f) => ({ ...f, target_price: e.target.value }))}
                placeholder="예: 30000"
                min="0"
              />
            </div>
            <div className="flex-1 min-w-[100px]">
              <label className={labelClass}>조건</label>
              <select
                className={inputClass}
                value={stockAlertForm.direction}
                onChange={(e) => setStockAlertForm((f) => ({ ...f, direction: e.target.value as "BELOW" | "ABOVE" }))}
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
                value={stockAlertForm.max_trigger_count}
                onChange={(e) => setStockAlertForm((f) => ({ ...f, max_trigger_count: e.target.value }))}
                min="1"
                placeholder="1"
              />
            </div>
          </div>
          <button
            onClick={() => createStockAlertMutation.mutate()}
            disabled={!selectedStock || !stockAlertForm.target_price || createStockAlertMutation.isPending}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {createStockAlertMutation.isPending ? "등록 중..." : "알림 추가"}
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
                    {Number(alert.target_price).toLocaleString("ko-KR")}원 {alert.direction === "BELOW" ? "이하" : "이상"}
                  </span>
                  <span className="ml-2 text-xs text-gray-400">{alert.trigger_count}/{alert.max_trigger_count}회</span>
                  {alert.is_active
                    ? <span className="ml-2 text-xs text-green-600 dark:text-green-400">활성</span>
                    : <span className="ml-2 text-xs text-gray-400">비활성</span>
                  }
                </div>
                <div className="flex items-center gap-1 ml-2 shrink-0">
                  {!alert.is_active && (
                    <button
                      onClick={() => reactivateStockAlertMutation.mutate(alert.id)}
                      disabled={reactivateStockAlertMutation.isPending}
                      className="px-2 py-1 text-xs text-blue-600 dark:text-blue-400 border border-blue-300 dark:border-blue-600 rounded-md hover:bg-blue-50 dark:hover:bg-blue-950 disabled:opacity-50 transition-colors"
                    >
                      재활성화
                    </button>
                  )}
                  <button
                    onClick={() => deleteStockAlertMutation.mutate(alert.id)}
                    disabled={deleteStockAlertMutation.isPending}
                    className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
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

      {/* 자동 정기매수 (DCA) */}
      <SectionCard title="자동 정기매수 (DCA)">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          매월 설정한 날에 지정 포트폴리오 비중대로 KIS 계좌에서 자동 매수합니다. 실거래 주문이 실행되므로 신중히 설정하세요.
        </p>
        <div className="flex items-center gap-3">
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={dcaForm.enabled}
              onChange={(e) => setDcaForm((f) => ({ ...f, enabled: e.target.checked }))}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full" />
          </label>
          <span className="text-sm text-gray-700 dark:text-gray-300 font-medium">
            {dcaForm.enabled ? "자동매수 활성화" : "자동매수 비활성화"}
          </span>
        </div>
        {dcaForm.enabled && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>실행일 (매월)</label>
                <select
                  className={inputClass}
                  value={dcaForm.day}
                  onChange={(e) => setDcaForm((f) => ({ ...f, day: e.target.value }))}
                >
                  {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                    <option key={d} value={d}>{d}일</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={labelClass}>월 매수 금액 (원)</label>
                <input
                  type="number"
                  className={inputClass}
                  value={dcaForm.amount}
                  onChange={(e) => setDcaForm((f) => ({ ...f, amount: e.target.value }))}
                  placeholder="500000"
                  min="0"
                />
              </div>
            </div>
            <div>
              <label className={labelClass}>비중 기준 포트폴리오</label>
              <select
                className={inputClass}
                value={dcaForm.portfolio_id}
                onChange={(e) => setDcaForm((f) => ({ ...f, portfolio_id: e.target.value }))}
              >
                <option value="">선택하세요</option>
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelClass}>매수 실행 계좌 (KIS)</label>
              <select
                className={inputClass}
                value={dcaForm.account_id}
                onChange={(e) => setDcaForm((f) => ({ ...f, account_id: e.target.value }))}
              >
                <option value="">선택하세요</option>
                {kisAccounts.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              {kisAccounts.length === 0 && (
                <p className="text-xs text-orange-500 dark:text-orange-400 mt-1">KIS 계좌를 먼저 등록해주세요.</p>
              )}
            </div>
          </div>
        )}
        <button
          onClick={() => saveDcaMutation.mutate()}
          disabled={saveDcaMutation.isPending}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saveDcaMutation.isPending ? "저장 중..." : "저장"}
        </button>
        {current?.auto_dca_last_executed_at && (
          <p className="text-xs text-gray-400 dark:text-gray-500">
            마지막 자동매수: {new Date(current.auto_dca_last_executed_at).toLocaleString("ko-KR")}
          </p>
        )}
      </SectionCard>

      {/* 리밸런싱 자동화 */}
      <SectionCard title="리밸런싱 자동화">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          리밸런싱 알림·자동 실행은 포트폴리오별로 설정합니다. 알림 주기, 이탈 임계값, 자동 주문 실행 여부를 포트폴리오 분석 탭에서 개별 설정할 수 있습니다.
        </p>
        <Link
          to="/portfolio?tab=포트폴리오분석"
          className="inline-flex items-center gap-2 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors"
        >
          포트폴리오 분석 탭에서 설정하기 →
        </Link>
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
