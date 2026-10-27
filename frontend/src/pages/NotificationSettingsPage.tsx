import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Bell, Mail, Activity } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchAlertHistory, type AlertHistoryItem } from "@/api/alerts";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";
import { useCollapsible } from "@/hooks/useCollapsible";
import { useGoalAchievementAlertsToggle } from "@/hooks/useGoalAchievementAlertsToggle";
import { useMonthlyReportAlertsToggle } from "@/hooks/useMonthlyReportAlertsToggle";
import { useYearEndTaxReminderToggle } from "@/hooks/useYearEndTaxReminderToggle";
import { useRecommendationDriftAlertToggle } from "@/hooks/useRecommendationDriftAlertToggle";
import { useChallengeRemindersToggle } from "@/hooks/useChallengeRemindersToggle";
import { ToggleRow } from "@/components/common/ToggleSwitch";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import EmptyState from "@/components/common/EmptyState";
import Tabs from "@/components/common/Tabs";
import RebalancingAlertSummaryCard from "@/components/settings/RebalancingAlertSummaryCard";
import { ExchangeRateAlertSection } from "@/components/settings/ExchangeRateAlertSection";
import { StockPriceAlertSection } from "@/components/settings/StockPriceAlertSection";
import { MarketSignalAlertSection } from "@/components/settings/MarketSignalAlertSection";
import { NotificationEmailSection } from "@/components/settings/NotificationEmailSection";
import { SectionCard } from "@/components/settings/shared";
import { REPORT_ALERT_FIELDS, countEnabled } from "@/utils/notificationAlertGroups";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import { invalidateSettingsData } from "@/utils/queryInvalidation";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { settingsQuery } from "@/api/queryOptions";

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
  CHALLENGE_REMINDER: "적립 챌린지 독려 알림",
  CHALLENGE_WRAPUP: "적립 챌린지 월간 결산",
  DCA_CASH_SHORTFALL: "적립매수 예수금 부족",
  YEAR_END_TAX_REMINDER: "연말 절세 리마인더",
};

const ALERT_HISTORY_PAGE_SIZE = 50;

function AlertHistorySection() {
  const [limit, setLimit] = useState(ALERT_HISTORY_PAGE_SIZE);
  const {
    data: history,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useQuery({
    queryKey: [...QUERY_KEYS.alertHistory, limit],
    queryFn: () => fetchAlertHistory({ limit }),
    staleTime: STALE_TIME.SHORT,
  });

  return (
    <SectionCard title="알림 발송 이력">
      {isLoading ? (
        <div className="h-20 bg-gray-50 dark:bg-gray-800 rounded animate-pulse" />
      ) : isError ? (
        <EmptyState
          title="알림 이력을 불러오지 못했습니다."
          action={{ label: "다시 시도", onClick: () => void refetch() }}
          compact
        />
      ) : !history || history.length === 0 ? (
        <p className="text-xs text-gray-400 dark:text-gray-500 py-2">
          발송된 알림 이력이 없습니다.
        </p>
      ) : (
        <>
          {/* 페이지 스크롤 안의 중첩 스크롤(max-h-64) 제거 — 개수는 아래 "더 보기"가 제한 (docs/plans/67 P1-17) */}
          <div className="space-y-2">
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
              className="w-full mt-2 min-h-[44px] text-sm font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/30 rounded-lg transition-colors disabled:opacity-50"
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
  const {
    enabled: challengeRemindersEnabled,
    toggle: toggleChallengeReminders,
    isPending: challengeRemindersPending,
  } = useChallengeRemindersToggle();

  const [isReportAlertsOpen, toggleReportAlertsOpen] = useCollapsible(
    false,
    "growlio:settings:report-alerts-open",
  );
  const [isMarketAlertsOpen, toggleMarketAlertsOpen, setMarketAlertsOpen] = useCollapsible(
    false,
    "growlio:settings:market-alerts-open",
  );
  useEffect(() => {
    // 딥링크 탭이 바뀔 때만 펼친다(setMarketAlertsOpen은 참조 고정)
    if (initialAlertTab === "시장 신호 알림") setMarketAlertsOpen(true);
  }, [initialAlertTab, setMarketAlertsOpen]);

  const reportAlertsEnabledCount = countEnabled([
    monthlyReportEnabled,
    yearEndTaxReminderEnabled,
    recommendationDriftAlertEnabled,
    challengeRemindersEnabled,
  ]);

  const { data: current } = useQuery(settingsQuery);

  const invalidateSettings = () => invalidateSettingsData(qc);

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

      {/* 카드 중첩(외곽 SectionCard 안에 SectionCard 3개)을 평탄화 — 각 섹션이 최상위 카드(U14) */}
      <SectionCard title="리밸런싱 자동화">
        <RebalancingAlertSummaryCard />
      </SectionCard>

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
        collapsedHint={`${REPORT_ALERT_FIELDS.length}개 중 ${reportAlertsEnabledCount}개 켜짐`}
      >
        <ToggleRow
          title="월간 리포트"
          description="매월 1일 전월 포트폴리오 요약을 이메일로 보내드립니다."
          checked={monthlyReportEnabled}
          disabled={monthlyReportPending}
          onChange={toggleMonthlyReport}
        />

        <div className="border-t border-gray-100 dark:border-gray-800 pt-2 mt-2">
          <ToggleRow
            title="연말 절세 리마인더"
            description="11~12월 매주 월요일, 활용 가능한 절세 방법(손실수확·공제한도)을 요약해 보내드립니다."
            checked={yearEndTaxReminderEnabled}
            disabled={yearEndTaxReminderPending}
            onChange={toggleYearEndTaxReminder}
          />
        </div>

        <div className="border-t border-gray-100 dark:border-gray-800 pt-2 mt-2">
          <ToggleRow
            title="추천 비중 변화 알림"
            description="매주 월요일, 목표 역산 추천 비중이 기준 포트폴리오의 현재 목표 비중과 유의미하게 달라지면 이메일/푸시로 알려드립니다."
            checked={recommendationDriftAlertEnabled}
            disabled={recommendationDriftAlertPending}
            onChange={toggleRecommendationDriftAlert}
          />
        </div>

        <div className="border-t border-gray-100 dark:border-gray-800 pt-2 mt-2">
          <ToggleRow
            title="적립 챌린지 알림"
            description="매월 25일 이번 달 적립 독려, 매월 1일 지난달 결산·연속 적립 현황을 이메일/푸시로 알려드립니다."
            checked={challengeRemindersEnabled}
            disabled={challengeRemindersPending}
            onChange={toggleChallengeReminders}
          />
        </div>
      </CollapsibleCard>

      {/* 토글 1개짜리 접힘 카드는 여는 수고만 늘려 바로 보이게 (docs/plans/67 P1-17) */}
      <div className="card">
        <ToggleRow
          title="목표 달성 알림"
          description="투자·입금·배당 목표를 달성하면 이메일·푸시로 알려드립니다."
          checked={goalAlertsEnabled}
          disabled={goalAlertsPending}
          onChange={toggleGoalAlerts}
        />
      </div>

      <CollapsibleCard
        icon={Activity}
        title="시장 모니터링"
        isOpen={isMarketAlertsOpen}
        onToggle={toggleMarketAlertsOpen}
        collapsedHint="시장 위험 신호 등급 전환 알림 + 매일 아침 요약 · 전술 국면 알림"
      >
        <MarketSignalAlertSection embedded />
        {/* 전술 국면 알림은 포트폴리오별 설정이라 여기선 위치만 알린다 — 시장 관련 알림을 한 목록에서 찾게(plans/64 S4) */}
        <div className="mt-4 border-t border-gray-100 dark:border-gray-700 pt-3">
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">전술 배분 국면 전환 알림</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            나스닥·S&P500 전술 배분을 켠 포트폴리오의 국면이 바뀌면 알려드려요. 포트폴리오마다 켜고
            끌 수 있어요.
          </p>
          <Link
            to={rebalancingUrl({ tab: "목표 조정", mode: "전술" })}
            className={`${TOUCH_TARGET_ROW} text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline`}
          >
            리밸런싱 › 목표 조정 › 전술에서 설정 →
          </Link>
        </div>
      </CollapsibleCard>

      {/* 알림 탭 */}
      <Tabs
        tabs={ALERT_TABS}
        activeTab={alertTab}
        onChange={setAlertTab}
        variant="pill"
        fullWidth
      />

      <div ref={alertTabContentRef}>
        {alertTab === "환율 알림" && <ExchangeRateAlertSection />}
        {alertTab === "주가 알림" && <StockPriceAlertSection />}
        {alertTab === "발송 이력" && <AlertHistorySection />}
      </div>
    </div>
  );
}
