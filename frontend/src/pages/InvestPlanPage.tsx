import { lazy, Suspense, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Settings2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useGoalSettings } from "@/hooks/useGoalSettings";
import { useDividendPlanSettings } from "@/hooks/useDividendPlanSettings";
import SkeletonCard from "@/components/common/SkeletonCard";
import { api } from "@/api/client";
import type { SettingsData } from "@/api/settings";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { TOUCH_TARGET_MIN, TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import { useSwipeTabs } from "@/hooks/useSwipeNavigation";

const DCAProjectionChart = lazy(() => import("../components/invest/DCAProjectionChart"));
const DividendPlanSection = lazy(() => import("../components/invest/DividendPlanSection"));
import ErrorBoundary from "@/components/ErrorBoundary";
import GoalTimelineCard from "@/components/invest/GoalTimelineCard";
import MonthlyAchievementTable from "@/components/invest/MonthlyAchievementTable";
import YearlyAchievementTable from "@/components/invest/YearlyAchievementTable";
import { fmtKrw } from "@/utils/format";
import { invalidateDcaData } from "@/utils/queryInvalidation";
import FormInput from "@/components/common/FormInput";
import ConfirmModal from "@/components/common/ConfirmModal";
import Modal from "@/components/common/Modal";
import CollapsibleSection from "@/components/common/CollapsibleSection";

const TABS = ["적립 계획", "배당 계획"] as const;
type Tab = (typeof TABS)[number];

export default function InvestPlanPage() {
  const queryClient = useQueryClient();
  const [showAllStats, setShowAllStats] = useState(false);
  const [monthlyOpen, setMonthlyOpen] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const rawTab = searchParams.get("tab");
  const activeTab: Tab = (TABS as readonly string[]).includes(rawTab ?? "")
    ? (rawTab as Tab)
    : "적립 계획";
  const setActiveTab = (tab: Tab) =>
    setSearchParams(
      (prev) => {
        prev.set("tab", tab);
        return prev;
      },
      { replace: true },
    );

  const { data: settingsData } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: () => api.get<SettingsData>("/settings").then((r) => r.data),
    staleTime: STALE_TIME.LONG,
  });

  const tabContentRef = useRef<HTMLDivElement>(null);
  useSwipeTabs(tabContentRef, TABS, activeTab, setActiveTab);

  const {
    data,
    isLoading,
    isError,
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

  const s = data?.settings;
  const isConfigured = data?.is_configured;
  const today = new Date().toISOString().slice(0, 7);
  const latestMonth = data?.projection_months
    .filter((d) => d.month <= today && d.has_data)
    .slice(-1)[0];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <SkeletonCard rows={2} height="h-6" />
        <SkeletonCard rows={7} height="h-10" />
        <SkeletonCard rows={5} height="h-5" />
      </div>
    );
  }

  if (isError && !data) {
    return (
      <div className="p-3 bg-red-50 dark:bg-red-950 rounded-lg text-sm text-red-700 dark:text-red-400 flex items-center justify-between">
        <span>데이터를 불러오지 못했습니다.</span>
        <button
          onClick={() => invalidateDcaData(queryClient)}
          className="underline font-medium ml-2"
        >
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 탭 전환 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-xl w-full sm:w-fit">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`flex-1 sm:flex-none px-4 py-2.5 text-sm font-medium rounded-lg transition-colors ${TOUCH_TARGET_MIN} ${
                activeTab === tab
                  ? "bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-50 shadow-sm"
                  : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <Link
            to="/rebalancing?rtab=포트폴리오"
            className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
          >
            목표 기반 포트폴리오 추천 보기 →
          </Link>
        </div>
      </div>

      <div ref={tabContentRef}>
        {/* 적립 계획 탭 */}
        {activeTab === "적립 계획" && (
          <>
            {/* 현재 설정 요약 */}
            <div className="card">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h2 className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                    적립 계획 설정
                  </h2>
                  <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
                    적립식 DCA 복리계산 및 목표 달성 현황
                  </p>
                </div>
                <button
                  onClick={openEdit}
                  className="shrink-0 flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  <Settings2 size={15} />
                  설정 편집
                </button>
              </div>
              <div
                className={`grid gap-4 ${showAllStats ? "grid-cols-3 sm:grid-cols-4 lg:grid-cols-7" : "grid-cols-2 sm:grid-cols-4 lg:grid-cols-7"}`}
              >
                {(
                  [
                    {
                      label: "월 적립액",
                      value: s?.monthly_deposit_amount ? fmtKrw(s.monthly_deposit_amount) : null,
                      priority: true,
                    },
                    {
                      label: "목표 연수익률",
                      value: s?.goal_annual_return_pct ? `${s.goal_annual_return_pct}%` : null,
                      priority: true,
                    },
                    {
                      label: "목표 금액",
                      value: s?.goal_amount ? fmtKrw(s.goal_amount) : null,
                      priority: true,
                    },
                    {
                      label: "연간 입금 목표 (대시보드 연동)",
                      value: settingsData?.annual_deposit_goal
                        ? fmtKrw(settingsData.annual_deposit_goal)
                        : null,
                      priority: true,
                    },
                    {
                      label: "투자 시작일",
                      value: s?.goal_start_date ?? null,
                      priority: false,
                    },
                    {
                      label: "시작시점 자산",
                      value: s?.goal_initial_amount ? fmtKrw(s.goal_initial_amount) : null,
                      emptyLabel: "스냅샷 자동",
                      priority: false,
                    },
                    {
                      label: "은퇴 목표시점 (대시보드 연동)",
                      value: settingsData?.retirement_target_year
                        ? `${settingsData.retirement_target_year}년`
                        : null,
                      priority: false,
                    },
                  ] as const
                ).map((stat) => (
                  <div
                    key={stat.label}
                    className={stat.priority || showAllStats ? "" : "hidden sm:block"}
                  >
                    <p className="text-xs text-gray-400 dark:text-gray-500">{stat.label}</p>
                    <p className="text-base font-bold text-gray-900 dark:text-gray-50 mt-0.5">
                      {stat.value ?? (
                        <span className="text-gray-300 dark:text-gray-600">
                          {"emptyLabel" in stat ? stat.emptyLabel : "미설정"}
                        </span>
                      )}
                    </p>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setShowAllStats((v) => !v)}
                className="sm:hidden mt-3 flex items-center gap-1 text-xs font-medium text-blue-600 dark:text-blue-400"
              >
                {showAllStats ? (
                  <>
                    접기 <ChevronUp size={13} />
                  </>
                ) : (
                  <>
                    더보기 <ChevronDown size={13} />
                  </>
                )}
              </button>
              <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
                연간 입금 목표·목표 연수익률·은퇴 목표 달성 현황은 대시보드에서 확인할 수 있습니다.
              </p>
              {data && !isConfigured && (
                <div className="mt-4 p-3 bg-yellow-50 dark:bg-yellow-950 rounded-lg text-sm text-yellow-800 dark:text-yellow-400">
                  월 적립액, 목표 수익률, 목표 금액, 투자 시작일을 모두 설정해야 분석을 볼 수
                  있습니다.{" "}
                  <button onClick={openEdit} className="underline font-medium">
                    지금 설정하기
                  </button>
                </div>
              )}
            </div>

            {isConfigured && data && (
              <ErrorBoundary variant="section">
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-[3fr_2fr] sm:items-start">
                  <Suspense fallback={<SkeletonCard rows={4} height="h-5" />}>
                    <DCAProjectionChart data={data.projection_months} />
                  </Suspense>
                  <div className="card divide-y divide-gray-100 dark:divide-gray-700">
                    <div className="pb-4">
                      <GoalTimelineCard
                        flat
                        timeline={data.goal_timeline}
                        goalAmount={s?.goal_amount ?? null}
                      />
                    </div>
                    <div className="py-4">
                      <YearlyAchievementTable flat data={data.yearly_achievements} />
                    </div>
                    <div className="pt-4">
                      <CollapsibleSection
                        isOpen={monthlyOpen}
                        onToggle={() => setMonthlyOpen((v) => !v)}
                        label="월별 상세 보기"
                        collapsedHint={
                          latestMonth
                            ? `최근 달(${latestMonth.month}) 달성율 ${latestMonth.achievement_pct !== null ? `${latestMonth.achievement_pct.toFixed(1)}%` : "—"}`
                            : undefined
                        }
                      >
                        <MonthlyAchievementTable flat data={data.projection_months} />
                      </CollapsibleSection>
                    </div>
                  </div>
                </div>
              </ErrorBoundary>
            )}
          </>
        )}

        {/* 배당 계획 탭 */}
        {activeTab === "배당 계획" && (
          <ErrorBoundary variant="section">
            <Suspense fallback={<SkeletonCard rows={5} height="h-5" />}>
              <DividendPlanSection onOpenSettings={openDividendEdit} />
            </Suspense>
          </ErrorBoundary>
        )}
      </div>

      {/* 적립 계획 설정 편집 모달 */}
      {editing && (
        <Modal title="적립 계획 설정 편집" onClose={handleCloseModal} size="md">
          <div className="overflow-y-auto overscroll-contain px-6 pb-6 pt-2 space-y-4 flex-1">
            {[
              {
                label: "월 적립액 (원)",
                key: "monthly_deposit_amount",
                placeholder: "500000",
                inputMode: "numeric",
              },
              {
                label: "목표 연수익률 (%)",
                key: "goal_annual_return_pct",
                placeholder: "8",
                hint: "대시보드 투자 목표 카드에 표시",
                inputMode: "decimal",
              },
              {
                label: "목표 금액 (원)",
                key: "goal_amount",
                placeholder: "500000000",
                inputMode: "numeric",
              },
              {
                label: "투자 시작일",
                key: "goal_start_date",
                placeholder: "2024-01-01",
                type: "date",
              },
              {
                label: "투자 시작시점 자산 (원)",
                key: "goal_initial_amount",
                placeholder: "100000000",
                hint: "비워두면 스냅샷 자동 사용",
                inputMode: "numeric",
              },
              {
                label: "연간 입금 목표 (원)",
                key: "annual_deposit_goal",
                placeholder: "24000000",
                hint: "대시보드 입금 달성률에 표시",
                inputMode: "numeric",
              },
              {
                label: "은퇴 목표시점 (연도)",
                key: "retirement_target_year",
                placeholder: "2045",
                hint: "대시보드 투자 목표 카드에 표시",
                inputMode: "numeric",
              },
            ].map(({ label, key, placeholder, type, hint, inputMode }) => (
              <FormInput
                key={key}
                label={label}
                type={type ?? "number"}
                inputMode={type ? undefined : (inputMode as "numeric" | "decimal")}
                value={form[key as keyof typeof form]}
                onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                placeholder={placeholder}
                hint={hint}
              />
            ))}

            <div className="flex gap-3 pt-4">
              <button
                onClick={handleCloseModal}
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors`}
              >
                취소
              </button>
              <button
                onClick={saveSettings}
                disabled={saving}
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} flex-1 px-4 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors`}
              >
                {saving ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </Modal>
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
          <div className="overflow-y-auto overscroll-contain px-6 pb-6 pt-2 space-y-4 flex-1">
            <FormInput
              label="목표 연간 배당금 (원)"
              type="number"
              inputMode="numeric"
              value={dividendForm.annual_dividend_goal}
              onChange={(e) =>
                setDividendForm((f) => ({ ...f, annual_dividend_goal: e.target.value }))
              }
              placeholder="10000000"
              hint="예상 연배당이 이 금액을 넘으면 목표 달성"
            />

            <div className="flex gap-3 pt-4">
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
            </div>
          </div>
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
