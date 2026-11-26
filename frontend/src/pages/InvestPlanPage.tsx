import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, DollarSign, PiggyBank, TrendingDown } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useGoalSettings } from "@/hooks/useGoalSettings";
import { useDividendPlanSettings } from "@/hooks/useDividendPlanSettings";
import SkeletonCard from "@/components/common/SkeletonCard";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";

const DCAProjectionChart = lazy(() => import("../components/invest/DCAProjectionChart"));
const DividendPlanSection = lazy(() => import("../components/invest/DividendPlanSection"));
const ChallengeSection = lazy(() => import("../components/invest/ChallengeSection"));
const TaxTabContainer = lazy(() => import("../components/portfolio-analysis/TaxTabContainer"));
const SavingsSimulatorCard = lazy(() => import("../components/invest/SavingsSimulatorCard"));
const FxPlanCard = lazy(() => import("../components/invest/FxPlanCard"));
const DipBuyCard = lazy(() => import("../components/invest/DipBuyCard"));
/** 낙폭 추매 카드 앵커 — 백엔드 `action_items_service._LINK_DIP_BUY`·`email_service.dip_buy_link`·푸시 `DCA_DIP_BUY`와 같은 해시 */
const DIP_BUY_ANCHOR = "dip-buy";
/** 해시 진입 스크롤을 한 번 더 맞추는 시점 — 지연 로드 차트·배너가 카드 위에서 높이를 바꾸는 시간 */
const ANCHOR_SCROLL_SETTLE_MS = 600;
import ErrorBoundary from "@/components/ErrorBoundary";
import GoalTimelineCard from "@/components/invest/GoalTimelineCard";
import AutoInvestStatusBanner from "@/components/invest/AutoInvestStatusBanner";
import MonthlyAchievementTable from "@/components/invest/MonthlyAchievementTable";
import DcaSettingsSummaryCard from "@/components/invest/DcaSettingsSummaryCard";
import GoalSettingsEditModal from "@/components/invest/GoalSettingsEditModal";
import DividendSettingsModal from "@/components/invest/DividendSettingsModal";
import YearlyAchievementTable from "@/components/invest/YearlyAchievementTable";
import { localMonth } from "@/utils/format";
import PageLoadError from "@/components/common/PageLoadError";
import ConfirmModal from "@/components/common/ConfirmModal";
import CollapsibleSection from "@/components/common/CollapsibleSection";
import CollapsibleCard from "@/components/common/CollapsibleCard";
import { useCollapsible } from "@/hooks/useCollapsible";
// 6단계 마법사(약 600줄)는 목표 최초 설정·재설정 때만 — 계획 탭 첫 진입 청크에서 분리(plans/125 E5)
import { useInView } from "@/hooks/useInView";
const GoalSettingWizard = lazy(() => import("@/components/invest/GoalSettingWizard"));
import Tabs from "@/components/common/Tabs";
import { rebalancingUrl } from "@/utils/rebalancingUrl";
import { FX_PLAN_DEFAULT_MONTHS, fxPlanQuery, settingsQuery } from "@/api/queryOptions";
import { INVEST_PLAN_TABS, type InvestPlanTab } from "@/constants/tabs";
import { legacyInvestPlanTab } from "@/utils/legacyTabRedirect";

// 절세는 자산 › 투자현황 › 세금에서 이동(plans/50 M1) — 목표·배당·절세 "계획"을 한 탭에 모은다
const TABS = INVEST_PLAN_TABS;
type Tab = InvestPlanTab;

/**
 * 알림(메일·푸시·홈 "지금 할 일")의 `#anchor`로 들어오면 접어 둔 카드도 펼친다(plans/121 C).
 * 펼침은 이번 진입(location.key)에만 적용하고 저장하지 않는다 — 링크 한 번에 사용자가 접어 둔 선택이 영구히
 * 바뀌지 않게, 같은 링크를 다시 눌러도(새 key) 다시 펼치게(plans/122 C1·C6)
 */
function useAnchoredCollapsible(anchor: string, storageKey: string, onDcaTab: boolean) {
  const [isOpen, toggle, setOpen] = useCollapsible(false, storageKey);
  const location = useLocation();
  const linked = location.hash === `#${anchor}` && onDcaTab;
  const [dismissedKey, setDismissedKey] = useState<string | null>(null);
  const forcedOpen = linked && dismissedKey !== location.key;
  const handleToggle = useCallback(() => {
    if (!forcedOpen) {
      toggle();
      return;
    }
    setDismissedKey(location.key);
    if (isOpen) setOpen(false);
  }, [forcedOpen, isOpen, location.key, setOpen, toggle]);
  return { open: isOpen || forcedOpen, linked, linkKey: location.key, handleToggle };
}

/** 해시 진입: 카드가 그려진 뒤 스크롤, 위쪽이 늦게 그려져 밀리므로 잠시 뒤 한 번 더(새 key 재진입에도) */
function useScrollToAnchor(anchor: string, linked: boolean, ready: boolean, linkKey: string) {
  useEffect(() => {
    if (!linked || !ready) return;
    const scroll = () => document.getElementById(anchor)?.scrollIntoView({ block: "start" });
    const frame = requestAnimationFrame(scroll);
    const settle = window.setTimeout(scroll, ANCHOR_SCROLL_SETTLE_MS);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
    };
  }, [anchor, linked, ready, linkKey]);
}

export default function InvestPlanPage() {
  const [monthlyOpen, setMonthlyOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const { hash } = useLocation();
  const rawTab = searchParams.get("tab");
  // 옛 환전 계획 링크(`?tab=적립 계획#fx-plan`, 발송된 메일·푸시)는 환전 탭으로(plans/149)
  const legacyTab = legacyInvestPlanTab(rawTab, hash);
  const activeTab: Tab =
    legacyTab ?? ((TABS as readonly string[]).includes(rawTab ?? "") ? (rawTab as Tab) : TABS[0]);
  const setActiveTab = (tab: Tab) =>
    setSearchParams(
      (prev) => {
        prev.set("tab", tab);
        return prev;
      },
      { replace: true },
    );

  // 추천 탭 "목표 설정하러 가기"에서 왔는지(U16) — 한 번만 읽고 URL에서 지운다(남기면 배너가 계속 뜸, plans/39 N7)
  const [fromRecommendation] = useState(() => searchParams.get("from") === "recommendation");
  useEffect(() => {
    if (!searchParams.has("from")) return;
    setSearchParams(
      (prev) => {
        prev.delete("from");
        return prev;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams]);

  // 옛 링크는 URL도 새 탭으로 바꾼다(해시 제거) — 탭을 옮겨도 다시 환전 탭으로 끌려가지 않게
  useEffect(() => {
    if (!legacyTab) return;
    setSearchParams(
      (prev) => {
        prev.set("tab", legacyTab);
        return prev;
      },
      { replace: true },
    );
  }, [legacyTab, setSearchParams]);

  // 저축 시뮬레이터는 목표와 무관한 보조 도구라 2단 탭 대신 최하단 접힘 카드로 둔다(U11)
  const [isSimulatorOpen, toggleSimulatorOpen] = useCollapsible(
    false,
    "growlio:invest:savingsSimulatorOpen",
  );
  // 낙폭 추매 안내 — 여윳돈을 쓰는 보조 도구라 기본 접힘(plans/147)
  const dipBuy = useAnchoredCollapsible(
    DIP_BUY_ANCHOR,
    "growlio:invest:dipBuyOpen",
    activeTab === "적립 계획",
  );

  const { data: settingsData } = useQuery(settingsQuery);

  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, TABS, activeTab, setActiveTab);

  const {
    data,
    isLoading,
    isError,
    refetch,
    editing,
    saving,
    showCloseConfirm,
    form,
    setForm,
    setShowCloseConfirm,
    setEditing,
    handleCloseModal,
    openEdit,
    saveSettings,
    wizardMode,
    wizardStep,
    setWizardStep,
    openWizard,
  } = useGoalSettings({ autoOpenWizard: activeTab === "적립 계획" });

  const {
    editing: dividendEditing,
    saving: dividendSaving,
    showCloseConfirm: dividendShowCloseConfirm,
    form: dividendForm,
    setForm: setDividendForm,
    setShowCloseConfirm: setDividendShowCloseConfirm,
    setEditing: setDividendEditing,
    handleCloseModal: handleDividendCloseModal,
    openEdit: openDividendEdit,
    saveSettings: saveDividendSettings,
  } = useDividendPlanSettings();

  useScrollToAnchor(DIP_BUY_ANCHOR, dipBuy.linked, !isLoading, dipBuy.linkKey);

  const s = data?.settings;
  const isConfigured = data?.is_configured;
  const today = localMonth();
  const latestMonth = data?.projection_months
    .filter((d) => d.month <= today && d.has_data)
    .slice(-1)[0];

  const [projectionChartRef, projectionChartInView] = useInView<HTMLDivElement>();

  // 적립 분석(dca-analysis)은 "적립 계획" 탭만 쓴다 — 예전엔 페이지 전체를 막아 챌린지·배당·절세 탭도 이 응답을
  // 기다렸다(plans/125 E7). 로딩·실패 표시는 그 탭 안에서만 한다.
  const dcaPending = isLoading;
  const dcaFailed = isError && !data;

  // 환전 카드 본문은 lazy 청크라 청크를 받고 나서야 요청이 나간다 — 탭에 들어오는 순간 요청을 함께 출발시킨다(plans/127).
  // 환전 탭은 적립 분석(dca-analysis)과 무관하게 그린다(plans/149)
  const queryClient = useQueryClient();
  const fxPlanVisible = activeTab === "환전";
  useEffect(() => {
    if (fxPlanVisible) void queryClient.prefetchQuery(fxPlanQuery(FX_PLAN_DEFAULT_MONTHS, null));
  }, [fxPlanVisible, queryClient]);

  // 낙폭 추매 카드는 적립 분석(dca-analysis)을 쓰지 않는다 — 분석이 실패해도 알림 링크(#dip-buy)로 들어온 사람이
  // 카드를 볼 수 있게 실패 화면 아래에도 그린다(plans/152 C2). 로딩 중엔 위 내용 높이가 바뀌어 스크롤이 어긋나므로 기다린다
  const dipBuySection = (
    <div id={DIP_BUY_ANCHOR} className="scroll-mt-4">
      <CollapsibleCard
        icon={TrendingDown}
        iconWrapClassName="bg-amber-50 dark:bg-amber-950"
        iconColorClassName="text-amber-600 dark:text-amber-400"
        title="낙폭 추매 안내"
        isOpen={dipBuy.open}
        onToggle={dipBuy.handleToggle}
        collapsedHint="지수가 고점 대비 내려가면 여윳돈을 구간별로 나눠 추매할 금액·종목 안내"
      >
        <ErrorBoundary variant="section">
          <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
            <DipBuyCard />
          </Suspense>
        </ErrorBoundary>
      </CollapsibleCard>
    </div>
  );

  return (
    <div className="space-y-6">
      <h1 className="sr-only">계획</h1>
      {/* 탭 전환 */}
      <div className="flex flex-wrap items-center gap-3">
        <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} variant="pill" fullWidth />
      </div>

      <div ref={tabContentRef}>
        {/* 적립 계획 탭 */}
        {activeTab === "적립 계획" && dcaPending && (
          <div className="space-y-6">
            <SkeletonCard rows={2} height="h-6" />
            <SkeletonCard rows={7} height="h-10" />
            <SkeletonCard rows={5} height="h-5" />
          </div>
        )}
        {activeTab === "적립 계획" && !dcaPending && dcaFailed && (
          // 실패한 적립 분석만 다시 조회한다 — invalidateDcaData는 설정·대시보드 등 8계열을 함께 지운다
          <div className="space-y-6">
            <PageLoadError message="데이터를 불러오지 못했습니다." onRetry={() => void refetch()} />
            {dipBuySection}
          </div>
        )}
        {activeTab === "적립 계획" && !dcaPending && !dcaFailed && (
          <div className="space-y-6">
            {/* 리밸런싱 추천 탭 "목표 설정하러 가기"에서 온 경우, 목표 저장 후 추천으로 돌아가는 길(U16) */}
            {fromRecommendation && isConfigured && (
              <Link
                to={rebalancingUrl({ tab: "목표 조정", mode: "추천" })}
                className="flex items-center justify-between gap-2 rounded-xl border border-teal-200 dark:border-teal-800/50 bg-teal-50 dark:bg-teal-950/30 px-4 py-3 text-sm font-medium text-teal-700 dark:text-teal-300"
              >
                목표가 설정됐어요 — 목표에 맞춘 추천 비중 보러 가기
                <ArrowRight size={14} className="shrink-0" />
              </Link>
            )}
            <div className="space-y-6">
              <DcaSettingsSummaryCard
                settings={s}
                annualDepositGoal={settingsData?.annual_deposit_goal ?? null}
                retirementTargetYear={settingsData?.retirement_target_year ?? null}
                showNotConfigured={!!data && !isConfigured}
                onOpenWizard={openWizard}
                onOpenEdit={openEdit}
              />

              <ErrorBoundary variant="section">
                <AutoInvestStatusBanner />
              </ErrorBoundary>

              {isConfigured && data && (
                <ErrorBoundary variant="section">
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-[3fr_2fr] sm:items-start">
                    {/* 추이 차트는 recharts(약 435KB) — 화면 근처에 왔을 때만 받는다(plans/125 E6) */}
                    <div ref={projectionChartRef}>
                      {projectionChartInView ? (
                        <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
                          <DCAProjectionChart
                            data={data.projection_months}
                            monthlyDepositAmount={s?.monthly_deposit_amount}
                            goalAnnualReturnPct={s?.goal_annual_return_pct}
                            goalAmount={s?.goal_amount}
                          />
                        </Suspense>
                      ) : (
                        <SkeletonCard rows={4} height="h-5" />
                      )}
                    </div>
                    <div className="card divide-y divide-gray-100 dark:divide-gray-700">
                      <div className="pb-4">
                        <GoalTimelineCard timeline={data.goal_timeline} />
                      </div>
                      <div className="py-4">
                        <YearlyAchievementTable data={data.yearly_achievements} />
                      </div>
                      <div className="pt-4">
                        <CollapsibleSection
                          isOpen={monthlyOpen}
                          onToggle={() => setMonthlyOpen((v) => !v)}
                          label="월별 상세 보기"
                          collapsedHint={
                            latestMonth
                              ? `최근 달(${latestMonth.month}) 달성률 ${latestMonth.achievement_pct !== null ? `${latestMonth.achievement_pct.toFixed(1)}%` : "—"}`
                              : undefined
                          }
                        >
                          <MonthlyAchievementTable data={data.projection_months} />
                        </CollapsibleSection>
                      </div>
                    </div>
                  </div>
                </ErrorBoundary>
              )}
            </div>

            {dipBuySection}

            <CollapsibleCard
              icon={PiggyBank}
              iconWrapClassName="bg-emerald-50 dark:bg-emerald-950"
              iconColorClassName="text-emerald-600 dark:text-emerald-400"
              title="절약 복리 시뮬레이터"
              isOpen={isSimulatorOpen}
              onToggle={toggleSimulatorOpen}
              collapsedHint="매달 아낀 돈·목돈이 복리로 얼마나 커지는지 계산"
            >
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
                  <SavingsSimulatorCard goalReturnPct={s?.goal_annual_return_pct ?? null} />
                </Suspense>
              </ErrorBoundary>
            </CollapsibleCard>
          </div>
        )}

        {/* 환전 탭 — 적립 계획의 해외 몫 달러 + 추가 환전(여행 등). 월 필요 달러는 서버가 적립 설정에서 계산 */}
        {activeTab === "환전" && (
          <section className="card">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg shrink-0 bg-sky-50 dark:bg-sky-950">
                <DollarSign size={16} className="text-sky-600 dark:text-sky-400" />
              </div>
              <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
                달러 환전 계획
              </h2>
            </div>
            <div className="mt-3">
              <ErrorBoundary variant="section">
                <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
                  <FxPlanCard onEditGoal={openEdit} />
                </Suspense>
              </ErrorBoundary>
            </div>
          </section>
        )}

        {/* 챌린지 탭 */}
        {activeTab === "챌린지" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
              <ChallengeSection settings={settingsData} />
            </Suspense>
          </ErrorBoundary>
        )}

        {/* 배당 계획 탭 */}
        {activeTab === "배당 계획" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard rows={5} height="h-5" />}>
              <DividendPlanSection onOpenSettings={openDividendEdit} />
            </Suspense>
          </ErrorBoundary>
        )}

        {/* 절세 탭 */}
        {activeTab === "절세" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard rows={4} height="h-4" />}>
              <TaxTabContainer />
            </Suspense>
          </ErrorBoundary>
        )}
      </div>

      {/* 적립 계획 설정 편집 마법사 (신규/재설정 가이드) */}
      {editing && wizardMode && (
        <Suspense fallback={null}>
          <GoalSettingWizard
            form={form}
            setForm={setForm}
            step={wizardStep}
            setStep={setWizardStep}
            onSave={saveSettings}
            onClose={handleCloseModal}
          />
        </Suspense>
      )}

      {/* 적립 계획 설정 편집 모달 (플랫 폼, 재설정용) */}
      {editing && !wizardMode && (
        <GoalSettingsEditModal
          form={form}
          setForm={setForm}
          saving={saving}
          onSave={saveSettings}
          onClose={handleCloseModal}
        />
      )}

      {showCloseConfirm && (
        <ConfirmModal
          message="저장하지 않은 변경사항이 있습니다. 닫으시겠습니까?"
          confirmLabel="닫기"
          cancelLabel="계속 편집"
          danger={false}
          onConfirm={() => {
            setShowCloseConfirm(false);
            setEditing(false);
          }}
          onCancel={() => setShowCloseConfirm(false)}
        />
      )}

      {/* 배당 계획 설정 편집 모달 */}
      {dividendEditing && (
        <DividendSettingsModal
          form={dividendForm}
          setForm={setDividendForm}
          saving={dividendSaving}
          onSave={saveDividendSettings}
          onClose={handleDividendCloseModal}
        />
      )}

      {dividendShowCloseConfirm && (
        <ConfirmModal
          message="저장하지 않은 변경사항이 있습니다. 닫으시겠습니까?"
          confirmLabel="닫기"
          cancelLabel="계속 편집"
          danger={false}
          onConfirm={() => {
            setDividendShowCloseConfirm(false);
            setDividendEditing(false);
          }}
          onCancel={() => setDividendShowCloseConfirm(false)}
        />
      )}
    </div>
  );
}
