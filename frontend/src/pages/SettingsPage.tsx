import { useState } from "react";
import { Sun, Moon, LogOut, Bell, Fingerprint, Wallet, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useBiometric } from "@/hooks/useBiometric";
import { isNativePlatform } from "@/utils/platform";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { type SettingsData } from "@/api/settings";
import { fetchAccounts } from "@/api/assets";
import { fetchAlertHistory, type AlertHistoryItem } from "@/api/alerts";
import { toast } from "@/utils/toast";
import { useThemeStore } from "@/stores/themeStore";
import { useLogout } from "@/hooks/useLogout";
import { ExchangeRateAlertSection } from "@/components/settings/ExchangeRateAlertSection";
import { isStockAccount } from "@/utils/accounts";
import { StockPriceAlertSection } from "@/components/settings/StockPriceAlertSection";
import { SectionCard, ConnectedBadge } from "@/components/settings/shared";
import RebalancingAlertListTab from "@/components/rebalancing/RebalancingAlertListTab";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { INPUT_MD, LABEL_MD } from "@/constants/inputStyles";

const ALERT_TYPE_LABELS: Record<string, string> = {
  EXCHANGE_RATE: "환율 알림",
  REBALANCING: "리밸런싱 알림",
  STOCK_PRICE: "주가 알림",
};

function AlertHistorySection() {
  const { data: history, isLoading } = useQuery({
    queryKey: QUERY_KEYS.alertHistory,
    queryFn: () => fetchAlertHistory({ limit: 50 }),
    staleTime: STALE_TIME.SHORT,
  });

  return (
    <SectionCard title="알림 발송 이력">
      {isLoading ? (
        <div className="h-20 bg-gray-50 dark:bg-gray-800 rounded animate-pulse" />
      ) : !history || history.length === 0 ? (
        <p className="text-xs text-gray-400 dark:text-gray-500 py-2">
          발송된 알림 이력이 없습니다.
        </p>
      ) : (
        <div className="max-h-64 overflow-y-auto space-y-2">
          {history.map((item: AlertHistoryItem) => (
            <div
              key={item.id}
              className="flex items-start gap-2.5 p-2.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg"
            >
              <Bell size={13} className="text-blue-400 mt-0.5 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-medium text-blue-600 dark:text-blue-400">
                    {ALERT_TYPE_LABELS[item.alert_type] ?? item.alert_type}
                  </span>
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    {new Date(item.created_at).toLocaleString("ko-KR", {
                      month: "numeric",
                      day: "numeric",
                      hour: "numeric",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <p className="text-xs text-gray-600 dark:text-gray-300 mt-0.5 leading-relaxed">
                  {item.message}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

const inputClass = `mt-1 w-full ${INPUT_MD}`;
const labelClass = LABEL_MD;

export default function SettingsPage() {
  const { isDark, toggle } = useThemeStore();
  const logout = useLogout();
  const { isAvailable, isEnabled, setEnabled } = useBiometric();
  const qc = useQueryClient();
  const [dart, setDart] = useState({ api_key: "" });
  const [saving, setSaving] = useState<string | null>(null);

  const { data: current } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => api.get<SettingsData>("/settings").then((r) => r.data),
    staleTime: STALE_TIME.LONG,
  });

  const { data: accounts = [] } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
    staleTime: STALE_TIME.MEDIUM,
    select: (data) => (Array.isArray(data) ? data : []),
  });

  const bankCount = accounts.filter((a) => a.asset_type === "BANK_ACCOUNT").length;
  const stockCount = accounts.filter((a) => isStockAccount(a.asset_type)).length;
  const realEstateCount = accounts.filter((a) => a.asset_type === "REAL_ESTATE").length;

  const invalidateSettings = () => qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });

  const saveDart = async () => {
    setSaving("dart");
    try {
      await api.put("/settings/dart", { api_key: dart.api_key });
      toast("DART API 키가 저장되었습니다", "success");
      void invalidateSettings();
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(null);
    }
  };

  const deleteDart = async () => {
    await api.delete("/settings/dart");
    toast("DART API 키가 삭제되었습니다", "success");
    void invalidateSettings();
  };

  const connectOpenBanking = async () => {
    const r = await api.get<{ authorize_url: string }>("/open-banking/connect");
    window.location.href = r.data.authorize_url;
  };

  const disconnectOpenBanking = async () => {
    await api.delete("/open-banking/disconnect");
    toast("오픈뱅킹 연결이 해제되었습니다", "success");
    void invalidateSettings();
  };

  return (
    <div className="space-y-6 max-w-xl">
      {/* 계좌 및 자산 관리 */}
      <Link
        to="/assets?section=management"
        className="flex items-center gap-4 p-4 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 hover:border-blue-300 dark:hover:border-blue-700 transition-colors"
      >
        <div className="p-2.5 bg-blue-50 dark:bg-blue-950 rounded-xl">
          <Wallet size={20} className="text-blue-600 dark:text-blue-400" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-800 dark:text-gray-200">계좌 및 자산 관리</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            은행 {bankCount}개 · 증권 {stockCount}개
            {realEstateCount > 0 ? ` · 부동산 ${realEstateCount}개` : ""}
          </p>
        </div>
        <ArrowRight size={16} className="text-gray-400 dark:text-gray-500 flex-shrink-0" />
      </Link>

      {/* DART OpenAPI */}
      <SectionCard
        title="DART OpenAPI (금융감독원)"
        badge={current?.has_dart ? <ConnectedBadge /> : undefined}
      >
        <p className="text-xs text-gray-500 dark:text-gray-400">
          opendart.fss.or.kr에서 발급받은 API 키를 입력하세요. 국내 주식 배당 데이터 조회에
          사용됩니다.
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
          <button
            onClick={saveDart}
            disabled={saving === "dart"}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving === "dart" ? "저장 중..." : "저장"}
          </button>
          {current?.has_dart && (
            <button
              onClick={deleteDart}
              className="px-5 py-2 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
            >
              삭제
            </button>
          )}
        </div>
      </SectionCard>

      {/* 오픈뱅킹 */}
      <SectionCard
        title="금융결제원 오픈뱅킹"
        badge={current?.has_open_banking ? <ConnectedBadge /> : undefined}
      >
        <p className="text-xs text-gray-500 dark:text-gray-400">
          오픈뱅킹을 연결하면 은행 통장 잔액을 자동으로 불러올 수 있습니다.
          {current?.ob_token_expires_at && (
            <> 토큰 만료: {new Date(current.ob_token_expires_at).toLocaleDateString("ko-KR")}</>
          )}
        </p>
        <div className="flex items-center gap-3">
          {current?.has_open_banking ? (
            <button
              onClick={disconnectOpenBanking}
              className="px-5 py-2 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
            >
              연결 해제
            </button>
          ) : (
            <button
              onClick={connectOpenBanking}
              className="bg-green-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-green-700 transition-colors"
            >
              오픈뱅킹 연결
            </button>
          )}
        </div>
      </SectionCard>

      {/* 알림 설정 통합 섹션 */}
      <div id="rebalancing-alerts">
        <SectionCard title="리밸런싱 자동화">
          <RebalancingAlertListTab />
        </SectionCard>
      </div>

      <ExchangeRateAlertSection
        userEmail={current?.user_email}
        onSettingsChange={invalidateSettings}
      />

      <StockPriceAlertSection />

      <AlertHistorySection />

      {/* 모바일 전용: 앱 설정 */}
      <div className="lg:hidden">
        <SectionCard title="앱 설정">
          <button
            onClick={toggle}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
            {isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
          </button>
          {isNativePlatform() && isAvailable && (
            <button
              onClick={() => setEnabled(!isEnabled)}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              aria-pressed={isEnabled}
            >
              <Fingerprint size={18} className={isEnabled ? "text-blue-500" : undefined} />
              생체 인증
              <span
                className={`ml-auto text-xs font-medium ${isEnabled ? "text-blue-500" : "text-gray-400"}`}
              >
                {isEnabled ? "켜짐" : "꺼짐"}
              </span>
            </button>
          )}
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
