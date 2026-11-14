import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowRight, DollarSign, PiggyBank } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useGoalSettings } from "@/hooks/useGoalSettings";
import { useDividendPlanSettings } from "@/hooks/useDividendPlanSettings";
import SkeletonCard from "@/components/common/SkeletonCard";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";

const DCAProjectionChart = lazy(() => import("../components/invest/DCAProjectionChart"));
const DividendPlanSection = lazy(() => import("../components/invest/DividendPlanSection"));
const ChallengeSection = lazy(() => import("../components/invest/ChallengeSection"));
const TaxTabContainer = lazy(() => import("../components/portfolio-analysis/TaxTabContainer"));
const SavingsSimulatorCard = lazy(() => import("../components/invest/SavingsSimulatorCard"));
const FxPlanCard = lazy(() => import("../components/invest/FxPlanCard"));
/** 환전 계획 카드 앵커 — 백엔드 `action_items_service._LINK_FX_PLAN`·`email_service.fx_plan_link`·푸시 딥링크와 같은 해시 */
const FX_PLAN_ANCHOR = "fx-plan";
/** 해시 진입 스크롤을 한 번 더 맞추는 시점 — 지연 로드 차트·배너가 카드 위에서 높이를 바꾸는 시간 */
const FX_PLAN_SCROLL_SETTLE_MS = 600;
import ErrorBoundary from "@/components/ErrorBoundary";
import GoalTimelineCard from "@/components/invest/GoalTimelineCard";
import AutoInvestStatusBanner from "@/components/invest/AutoInvestStatusBanner";
import MonthlyAchievementTable from "@/components/invest/MonthlyAchievementTable";
import DcaSettingsSummaryCard from "@/components/invest/DcaSettingsSummaryCard";
import GoalSettingsEditModal from "@/components/invest/GoalSettingsEditModal";
import YearlyAchievementTable from "@/components/invest/YearlyAchievementTable";
import { fmtKrwPreview, localMonth } from "@/utils/format";
import PageLoadError from "@/components/common/PageLoadError";
import FormInput from "@/components/common/FormInput";
import ConfirmModal from "@/components/common/ConfirmModal";
import Modal, { ModalBody, ModalFooter } from "@/components/common/Modal";
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

// 절세는 자산 › 투자현황 › 세금에서 이동(plans/50 M1) — 목표·배당·절세 "계획"을 한 탭에 모은다
const TABS = INVEST_PLAN_TABS;
type Tab = InvestPlanTab;

export default function InvestPlanPage() {
  const [monthlyOpen, setMonthlyOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const activeTab: Tab = (TABS as readonly string[]).includes(rawTab ?? "")
    ? (rawTab as Tab)
    : TABS[0];
  const setActiveTab = (tab: Tab) =>
    setSearchParams(
      (prev) => {
        prev.set("tab", tab);
        return prev;
      },
      { replace: true },
    );

  // 리밸런싱 추천 탭 "목표 설정하러 가기"에서 왔는지(U16) — 진입 시 한 번만 읽고 URL에서는 지운다.
  // 파라미터가 남아 있으면 새로고침·뒤로가기로 다시 들어와도 "추천 보러 가기" 배너가 계속 떴다(plans/39 N7).
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

  // 저축 시뮬레이터는 목표와 무관한 보조 도구라 2단 탭 대신 최하단 접힘 카드로 둔다(U11)
  const [isSimulatorOpen, toggleSimulatorOpen] = useCollapsible(
    false,
    "growlio:invest:savingsSimulatorOpen",
  );
  // 달러 환전 계획 — 해외 적립 보조 도구라 기본 접힘(plans/96)
  const [isFxPlanOpen, toggleFxPlanOpen, setFxPlanOpen] = useCollapsible(
    false,
    "growlio:invest:fxPlanOpen",
  );

  const { data: settingsData } = useQuery(settingsQuery);

  // 환전 계획 알림(메일·푸시·홈 "지금 할 일")의 `#fx-plan`으로 들어오면 접어 둔 카드도 펼치고 스크롤한다(plans/121 C).
  // 펼침은 이번 진입(location.key)에만 적용하고 저장하지 않는다 — 링크 한 번에 사용자가 접어 둔 선택이 영구히
  // 바뀌지 않게, 같은 링크를 다시 눌러도(새 key) 다시 펼치게(plans/122 C1·C6)
  const location = useLocation();
  const fxPlanLinked = location.hash === `#${FX_PLAN_ANCHOR}` && activeTab === "적립 계획";
  const [fxPlanDismissedKey, setFxPlanDismissedKey] = useState<string | null>(null);
  const fxPlanForcedOpen = fxPlanLinked && fxPlanDismissedKey !== location.key;
  const handleFxPlanToggle = useCallback(() => {
    if (!fxPlanForcedOpen) {
      toggleFxPlanOpen();
      return;
    }
    setFxPlanDismissedKey(location.key);
    if (isFxPlanOpen) setFxPlanOpen(false);
  }, [fxPlanForcedOpen, isFxPlanOpen, location.key, setFxPlanOpen, toggleFxPlanOpen]);

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
  } = useGoalSettings();

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

  // `#fx-plan`으로 들어왔으면 페이지 로딩이 끝나 카드가 그려진 뒤 그 위치로 스크롤한다. 위쪽 배너·차트가
  // 늦게 그려져 카드를 밀어내므로 잠시 뒤 한 번 더 맞춘다. 같은 링크 재진입(새 key)에도 다시 돈다
  const linkKey = location.key;
  useEffect(() => {
    if (!fxPlanLinked || isLoading) return;
    const scroll = () =>
      document.getElementById(FX_PLAN_ANCHOR)?.scrollIntoView({ block: "start" });
    const frame = requestAnimationFrame(scroll);
    const settle = window.setTimeout(scroll, FX_PLAN_SCROLL_SETTLE_MS);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
    };
  }, [fxPlanLinked, isLoading, linkKey]);

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

  // 카드 본문은 lazy 청크라 열린 뒤 청크를 받고 나서야 요청이 나간다 — 펼쳐지는 순간 요청을 함께 출발시킨다(plans/127).
  // 적립 분석이 실패하면 카드를 그리지 않으므로 받지 않는다(plans/128 A4)
  const queryClient = useQueryClient();
  const fxPlanVisible =
    activeTab === "적립 계획" && !dcaFailed && (isFxPlanOpen || fxPlanForcedOpen);
  useEffect(() => {
    if (fxPlanVisible) void queryClient.prefetchQuery(fxPlanQuery(FX_PLAN_DEFAULT_MONTHS, null));
  }, [fxPlanVisible, queryClient]);

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
          <PageLoadError message="데이터를 불러오지 못했습니다." onRetry={() => void refetch()} />
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

            <div id={FX_PLAN_ANCHOR} className="scroll-mt-4">
              <CollapsibleCard
                icon={DollarSign}
                iconWrapClassName="bg-sky-50 dark:bg-sky-950"
                iconColorClassName="text-sky-600 dark:text-sky-400"
                title="달러 환전 계획"
                isOpen={isFxPlanOpen || fxPlanForcedOpen}
                onToggle={handleFxPlanToggle}
                collapsedHint="지금 환율이 1년 중 어디쯤인지 보고 해외 적립용 달러를 나눠 환전"
              >
                <ErrorBoundary variant="section">
                  <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
                    <FxPlanCard onEditGoal={openEdit} />
                  </Suspense>
                </ErrorBoundary>
              </CollapsibleCard>
            </div>

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
        <Modal title="배당 계획 설정" onClose={handleDividendCloseModal} size="md">
          <ModalBody padding="px-6 pb-6 pt-2" className="space-y-4">
            <FormInput
              label="목표 연간 배당금 (원)"
              type="number"
              inputMode="numeric"
              value={dividendForm.annual_dividend_goal}
              onChange={(e) =>
                setDividendForm((f) => ({ ...f, annual_dividend_goal: e.target.value }))
              }
              placeholder="10000000"
              preview={
                dividendForm.annual_dividend_goal
                  ? fmtKrwPreview(Number(dividendForm.annual_dividend_goal))
                  : undefined
              }
              hint="예상 연배당이 이 금액을 넘으면 목표 달성"
            />
          </ModalBody>
          <ModalFooter>
            <button
              onClick={handleDividendCloseModal}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
            >
              취소
            </button>
            <button
              onClick={saveDividendSettings}
              disabled={dividendSaving}
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
            >
              {dividendSaving ? "저장 중..." : "저장"}
            </button>
          </ModalFooter>
        </Modal>
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
