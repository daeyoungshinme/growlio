import { useEffect, useRef, useState } from "react";
import {
  Sun,
  Moon,
  LogOut,
  Bell,
  Fingerprint,
  LayoutGrid,
  UserX,
  Landmark,
  Target,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { isNativePlatform } from "@/utils/platform";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { type SettingsData } from "@/api/settings";
import { fetchAlertHistory, type AlertHistoryItem } from "@/api/alerts";
import { toast } from "@/utils/toast";
import { useThemeStore } from "@/stores/themeStore";
import { useLogout } from "@/hooks/useLogout";
import { useBiometric } from "@/hooks/useBiometric";
import { retryPushRegistration, disablePushNotifications } from "@/hooks/usePushNotifications";
import { usePushNotificationStore } from "@/stores/pushNotificationStore";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { ExchangeRateAlertSection } from "@/components/settings/ExchangeRateAlertSection";
import { StockPriceAlertSection } from "@/components/settings/StockPriceAlertSection";
import { MarketSignalAlertSection } from "@/components/settings/MarketSignalAlertSection";
import { NotificationEmailSection } from "@/components/settings/NotificationEmailSection";
import DeleteAccountModal from "@/components/settings/DeleteAccountModal";
import { SectionCard, ConnectedBadge } from "@/components/settings/shared";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { INPUT_MD, LABEL_MD } from "@/constants/inputStyles";
import { TOUCH_TARGET_MIN, TOUCH_TARGET_ROW } from "@/constants/uiSizes";

const RISK_TOLERANCE_LABELS: Record<string, string> = {
  CONSERVATIVE: "보수적",
  BALANCED: "중립",
  AGGRESSIVE: "공격적",
};

function SettingsLinkRow({
  to,
  icon,
  label,
  status,
  statusClassName,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  status: string;
  statusClassName?: string;
}) {
  return (
    <Link
      to={to}
      className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
    >
      {icon}
      <span className="flex-1 min-w-0 truncate">{label}</span>
      <span className={`text-xs shrink-0 ${statusClassName ?? "text-gray-400 dark:text-gray-500"}`}>
        {status}
      </span>
      <ChevronRight size={16} className="text-gray-300 dark:text-gray-600 shrink-0" />
    </Link>
  );
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  EXCHANGE_RATE: "환율 알림",
  REBALANCING: "리밸런싱 알림",
  STOCK_PRICE: "주가 알림",
  MARKET_SIGNAL: "시장 신호 알림",
  GOAL_ASSET: "자산 목표 달성 알림",
  GOAL_DEPOSIT: "입금 목표 달성 알림",
  GOAL_DIVIDEND: "배당 목표 달성 알림",
};

const ALERT_HISTORY_PAGE_SIZE = 50;

function AlertHistorySection() {
  const [limit, setLimit] = useState(ALERT_HISTORY_PAGE_SIZE);
  const {
    data: history,
    isLoading,
    isFetching,
  } = useQuery({
    queryKey: [...QUERY_KEYS.alertHistory, limit],
    queryFn: () => fetchAlertHistory({ limit }),
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
        <>
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
          {history.length >= limit && (
            <button
              onClick={() => setLimit((l) => l + ALERT_HISTORY_PAGE_SIZE)}
              disabled={isFetching}
              className="w-full mt-2 py-2 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30 rounded-lg transition-colors disabled:opacity-50"
            >
              {isFetching ? "불러오는 중..." : "더 보기"}
            </button>
          )}
        </>
      )}
    </SectionCard>
  );
}

const inputClass = `mt-1 w-full ${INPUT_MD}`;
const labelClass = LABEL_MD;

const ALERT_TABS = ["환율 알림", "주가 알림", "시장 신호 알림", "발송 이력"] as const;
type AlertTab = (typeof ALERT_TABS)[number];

export default function SettingsPage() {
  const { isDark, toggle } = useThemeStore();
  const [searchParams] = useSearchParams();
  const initialAlertTab = searchParams.get("atab");
  const [alertTab, setAlertTab] = useState<AlertTab>(
    (ALERT_TABS as readonly string[]).includes(initialAlertTab ?? "")
      ? (initialAlertTab as AlertTab)
      : "환율 알림",
  );
  const alertSectionRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!initialAlertTab) return;
    const timer = setTimeout(() => {
      alertSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
    return () => clearTimeout(timer);
  }, [initialAlertTab]);

  const alertTabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(alertTabContentRef, ALERT_TABS, alertTab, setAlertTab);

  const logout = useLogout();
  const { isAvailable, isEnabled, setEnabled } = useBiometric();
  const pushStatus = usePushNotificationStore((s) => s.status);
  const qc = useQueryClient();
  const [dart, setDart] = useState({ api_key: "" });
  const [saving, setSaving] = useState<string | null>(null);
  const [showDeleteAccount, setShowDeleteAccount] = useState(false);

  const { data: current } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => api.get<SettingsData>("/settings").then((r) => r.data),
    staleTime: STALE_TIME.LONG,
  });

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

  const goalFieldsSetCount = current
    ? [
        current.goal_amount,
        current.annual_deposit_goal,
        current.monthly_deposit_amount,
        current.retirement_target_year,
        current.annual_dividend_goal,
      ].filter((v) => v !== null && v !== undefined).length
    : 0;
  const goalSummary = !current
    ? "불러오는 중..."
    : goalFieldsSetCount > 0
      ? `목표 ${goalFieldsSetCount}개 설정됨`
      : "설정된 목표 없음";

  const recommendationSummary = current
    ? `${RISK_TOLERANCE_LABELS[current.goal_risk_tolerance] ?? current.goal_risk_tolerance} · 후보 ${current.goal_candidate_tickers.length}개`
    : "불러오는 중...";

  return (
    <div className="space-y-6 max-w-xl">
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

      {/* 다른 설정 — 계좌 연동/목표/추천 옵션은 각 기능 페이지에서 편집, 여기서는 상태 요약 + 딥링크만 제공 */}
      <SectionCard title="다른 설정">
        <SettingsLinkRow
          to="/assets?tab=계좌관리"
          icon={<Landmark size={18} className="text-gray-400 dark:text-gray-500" />}
          label="계좌 연동 (KIS/키움)"
          status={!current ? "불러오는 중..." : current.has_kis ? "연결됨" : "미연결"}
          statusClassName={
            current?.has_kis
              ? "text-green-600 dark:text-green-400"
              : "text-gray-400 dark:text-gray-500"
          }
        />
        <SettingsLinkRow
          to="/invest-plan?tab=적립 계획"
          icon={<Target size={18} className="text-gray-400 dark:text-gray-500" />}
          label="투자·입금·배당 목표"
          status={goalSummary}
        />
        <SettingsLinkRow
          to="/rebalancing?rtab=포트폴리오"
          icon={<Sparkles size={18} className="text-gray-400 dark:text-gray-500" />}
          label="목표 역산 추천 옵션"
          status={recommendationSummary}
        />
      </SectionCard>

      {/* 알림 설정 그룹 */}
      <div ref={alertSectionRef}>
        <SectionCard title="알림 설정">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            리밸런싱 비중 이탈 알림 및 자동 실행 설정은{" "}
            <Link
              to="/rebalancing?rtab=포트폴리오"
              className="text-blue-600 dark:text-blue-400 underline"
            >
              리밸런싱 탭
            </Link>
            에서 포트폴리오별로 설정합니다.
          </p>

          {/* 공통 알림 수신 이메일 — 전체 알림 유형에 적용 */}
          <NotificationEmailSection
            userEmail={current?.user_email}
            onSettingsChange={invalidateSettings}
          />

          {/* 알림 탭 */}
          <div className="flex gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-xl">
            {ALERT_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => setAlertTab(tab)}
                className={`flex-1 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${TOUCH_TARGET_MIN} ${
                  alertTab === tab
                    ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-50 shadow-sm"
                    : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>

          <div ref={alertTabContentRef}>
            {alertTab === "환율 알림" && <ExchangeRateAlertSection />}
            {alertTab === "주가 알림" && <StockPriceAlertSection />}
            {alertTab === "시장 신호 알림" && <MarketSignalAlertSection />}
            {alertTab === "발송 이력" && <AlertHistorySection />}
          </div>
        </SectionCard>
      </div>

      {/* 앱 설정 */}
      <div>
        <SectionCard title="앱 설정">
          {isNativePlatform() && (
            <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400 mb-1">
              <LayoutGrid size={18} className="shrink-0 mt-0.5" />
              <p className="text-xs leading-relaxed">
                홈 화면을 길게 눌러 "위젯 추가"에서 Growlio를 선택하면 자산 현황을 홈 화면에서 바로
                확인할 수 있어요.
              </p>
            </div>
          )}
          <button
            onClick={toggle}
            className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
            {isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
          </button>
          {isNativePlatform() && isAvailable && (
            <button
              onClick={() => setEnabled(!isEnabled)}
              className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
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
          {isNativePlatform() && (
            <>
              <button
                onClick={() => {
                  if (pushStatus === "registered") {
                    void disablePushNotifications();
                  } else {
                    void retryPushRegistration();
                  }
                }}
                disabled={pushStatus === "requesting"}
                className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-50 ${TOUCH_TARGET_ROW}`}
                aria-pressed={pushStatus === "registered"}
              >
                <Bell
                  size={18}
                  className={pushStatus === "registered" ? "text-blue-500" : undefined}
                />
                푸시 알림
                <span
                  className={`ml-auto text-xs font-medium ${pushStatus === "registered" ? "text-blue-500" : "text-gray-400"}`}
                >
                  {pushStatus === "registered"
                    ? "켜짐"
                    : pushStatus === "requesting"
                      ? "확인 중..."
                      : "꺼짐"}
                </span>
              </button>
              {pushStatus === "denied" && (
                <p className="px-3 -mt-1 mb-1 text-xs text-amber-600 dark:text-amber-400">
                  알림 권한이 거부되어 있어요. 기기 설정 &gt; 앱 &gt; Growlio에서 알림을
                  허용해주세요.
                </p>
              )}
            </>
          )}
          <button
            onClick={logout}
            className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors ${TOUCH_TARGET_ROW}`}
          >
            <LogOut size={18} />
            로그아웃
          </button>
          <div className="border-t border-gray-100 dark:border-gray-800 pt-3">
            <button
              onClick={() => setShowDeleteAccount(true)}
              className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors ${TOUCH_TARGET_ROW}`}
            >
              <UserX size={18} />
              회원 탈퇴
            </button>
          </div>
        </SectionCard>
      </div>

      {showDeleteAccount && <DeleteAccountModal onClose={() => setShowDeleteAccount(false)} />}
    </div>
  );
}
