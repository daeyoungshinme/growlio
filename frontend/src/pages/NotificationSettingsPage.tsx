import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Bell, Mail, TrendingUp, Activity } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { type SettingsData } from "@/api/settings";
import { fetchAlertHistory, type AlertHistoryItem } from "@/api/alerts";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useGoalAchievementAlertsToggle } from "@/hooks/useGoalAchievementAlertsToggle";
import { useMonthlyReportAlertsToggle } from "@/hooks/useMonthlyReportAlertsToggle";
import { useYearEndTaxReminderToggle } from "@/hooks/useYearEndTaxReminderToggle";
import { useRecommendationDriftAlertToggle } from "@/hooks/useRecommendationDriftAlertToggle";
import { ToggleSwitch } from "@/components/common/ToggleSwitch";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import RebalancingAlertSummaryCard from "@/components/settings/RebalancingAlertSummaryCard";
import { ExchangeRateAlertSection } from "@/components/settings/ExchangeRateAlertSection";
import { StockPriceAlertSection } from "@/components/settings/StockPriceAlertSection";
import { MarketSignalAlertSection } from "@/components/settings/MarketSignalAlertSection";
import { NotificationEmailSection } from "@/components/settings/NotificationEmailSection";
import { SectionCard } from "@/components/settings/shared";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN, TOUCH_TARGET_ROW } from "@/constants/uiSizes";

const ALERT_TYPE_LABELS: Record<string, string> = {
  EXCHANGE_RATE: "환율 알림",
  REBALANCING: "리밸런싱 알림",
  STOCK_PRICE: "주가 알림",
  MARKET_SIGNAL: "시장 신호 알림",
  MARKET_SIGNAL_DIGEST: "시장신호 매일 요약",
  GOAL_ASSET: "자산 목표 달성 알림",
  GOAL_DEPOSIT: "입금 목표 달성 알림",
  GOAL_DIVIDEND: "배당 목표 달성 알림",
  MONTHLY_REPORT: "월간 리포트",
  RECOMMENDATION_DRIFT: "추천 비중 변화 알림",
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

const ALERT_TABS = ["환율 알림", "주가 알림", "발송 이력"] as const;
type AlertTab = (typeof ALERT_TABS)[number];

/** 설정탭 "알림 설정" 딥링크 진입점 — 카테고리별 그룹(정기 리포트·요약/즉시 알림/시장 모니터링) +
 * 환율/주가/발송이력 탭을 별도 라우트로 분리해 `SettingsPage.tsx`의 3중 중첩(SectionCard›
 * CollapsibleCard×3›내부 pill탭)을 완화한다(2026-07-26). */
export default function NotificationSettingsPage() {
  const [searchParams] = useSearchParams();
  const initialAlertTab = searchParams.get("atab");
  const [alertTab, setAlertTab] = useState<AlertTab>(
    (ALERT_TABS as readonly string[]).includes(initialAlertTab ?? "")
      ? (initialAlertTab as AlertTab)
      : "환율 알림",
  );

  const alertTabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(alertTabContentRef, ALERT_TABS, alertTab, setAlertTab);

  const qc = useQueryClient();
  const {
    enabled: goalAlertsEnabled,
    toggle: toggleGoalAlerts,
    isPending: goalAlertsPending,
  } = useGoalAchievementAlertsToggle();
  const {
    enabled: monthlyReportEnabled,
    toggle: toggleMonthlyReport,
    isPending: monthlyReportPending,
  } = useMonthlyReportAlertsToggle();
  const {
    enabled: yearEndTaxReminderEnabled,
    toggle: toggleYearEndTaxReminder,
    isPending: yearEndTaxReminderPending,
  } = useYearEndTaxReminderToggle();
  const {
    enabled: recommendationDriftAlertEnabled,
    toggle: toggleRecommendationDriftAlert,
    isPending: recommendationDriftAlertPending,
  } = useRecommendationDriftAlertToggle();

  const [isReportAlertsOpen, toggleReportAlertsOpen] = useCollapsible(
    false,
    "growlio:settings:report-alerts-open",
  );
  const [isGoalAlertsOpen, toggleGoalAlertsOpen] = useCollapsible(
    false,
    "growlio:settings:goal-alerts-open",
  );
  const [isMarketAlertsOpen, toggleMarketAlertsOpen, setMarketAlertsOpen] = useCollapsible(
    false,
    "growlio:settings:market-alerts-open",
  );
  useEffect(() => {
    if (initialAlertTab === "시장 신호 알림") setMarketAlertsOpen(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAlertTab]);

  const reportAlertsEnabledCount = [
    monthlyReportEnabled,
    yearEndTaxReminderEnabled,
    recommendationDriftAlertEnabled,
  ].filter(Boolean).length;
  const instantAlertsEnabledCount = [goalAlertsEnabled].filter(Boolean).length;

  const { data: current } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => api.get<SettingsData>("/settings").then((r) => r.data),
    staleTime: STALE_TIME.LONG,
  });

  const invalidateSettings = () => qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="sr-only">알림 설정</h1>
      <Link
        to="/settings"
        className={`gap-2 -ml-1 px-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 ${TOUCH_TARGET_ROW} w-auto inline-flex`}
      >
        <ArrowLeft size={18} />
        설정
      </Link>

      <SectionCard title="알림 설정">
        <RebalancingAlertSummaryCard />

        {/* 공통 알림 수신 이메일 — 전체 알림 유형에 적용 */}
        <NotificationEmailSection
          userEmail={current?.user_email}
          onSettingsChange={invalidateSettings}
        />

        <CollapsibleCard
          icon={Mail}
          title="정기 리포트·요약"
          isOpen={isReportAlertsOpen}
          onToggle={toggleReportAlertsOpen}
          collapsedHint={`3개 중 ${reportAlertsEnabledCount}개 켜짐`}
        >
          <div>
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">월간 리포트</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              매월 1일 전월 포트폴리오 요약을 이메일로 보내드립니다.
            </p>
            <ToggleSwitch
              checked={monthlyReportEnabled}
              disabled={monthlyReportPending}
              onChange={toggleMonthlyReport}
              ariaLabel="월간 리포트"
            />
          </div>

          <div className="border-t border-gray-100 dark:border-gray-800 pt-3 mt-3">
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">연말 절세 리마인더</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              11~12월 매주 월요일, 활용 가능한 절세 방법(손실수확·공제한도)을 요약해 보내드립니다.
            </p>
            <ToggleSwitch
              checked={yearEndTaxReminderEnabled}
              disabled={yearEndTaxReminderPending}
              onChange={toggleYearEndTaxReminder}
              ariaLabel="연말 절세 리마인더"
            />
          </div>

          <div className="border-t border-gray-100 dark:border-gray-800 pt-3 mt-3">
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">추천 비중 변화 알림</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              매주 월요일, 목표 역산 추천 비중이 타겟 포트폴리오의 현재 목표 비중과 유의미하게
              달라지면 이메일/푸시로 알려드립니다.
            </p>
            <ToggleSwitch
              checked={recommendationDriftAlertEnabled}
              disabled={recommendationDriftAlertPending}
              onChange={toggleRecommendationDriftAlert}
              ariaLabel="추천 비중 변화 알림"
            />
          </div>
        </CollapsibleCard>

        <CollapsibleCard
          icon={TrendingUp}
          title="즉시 알림"
          isOpen={isGoalAlertsOpen}
          onToggle={toggleGoalAlertsOpen}
          collapsedHint={`1개 중 ${instantAlertsEnabledCount}개 켜짐`}
        >
          <div>
            <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">목표 달성 알림</p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              투자·입금·배당 목표를 달성하면 이메일·푸시로 알려드립니다.
            </p>
            <ToggleSwitch
              checked={goalAlertsEnabled}
              disabled={goalAlertsPending}
              onChange={toggleGoalAlerts}
              ariaLabel="목표 달성 알림"
            />
          </div>
        </CollapsibleCard>

        <CollapsibleCard
          icon={Activity}
          title="시장 모니터링"
          isOpen={isMarketAlertsOpen}
          onToggle={toggleMarketAlertsOpen}
          collapsedHint="시장 위험 신호 등급 전환 알림 + 매일 아침 요약"
        >
          <MarketSignalAlertSection embedded />
        </CollapsibleCard>

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
          {alertTab === "발송 이력" && <AlertHistorySection />}
        </div>
      </SectionCard>
    </div>
  );
}
