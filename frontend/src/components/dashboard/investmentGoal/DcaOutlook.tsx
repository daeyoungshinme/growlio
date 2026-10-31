import { Link } from "react-router-dom";
import { ArrowRight, TrendingDown, TrendingUp } from "lucide-react";
import { fmtKrw, fmtMonth } from "@/utils/format";
import CollapsibleSection from "@/components/common/CollapsibleSection";
import type { DCAAnalysisData } from "@/api/invest";
import { TOUCH_HEIGHT_MIN, TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

type GoalTimeline = DCAAnalysisData["goal_timeline"] | undefined;

interface OutlookProps {
  timeline: GoalTimeline;
  currentProgressPct: number | null | undefined;
  goalAmountDisplay: number | null | undefined;
  goalGapAmount: number | null;
  hasData: boolean;
}

/** "전체 진행률" 헤드라인 — 모바일 헤더/데스크탑 3열 그리드 양쪽에서 값·서식이 동일해야 하므로
 * 텍스트 크기만 파라미터화해 하나로 공유한다 (예전엔 sm:hidden/hidden sm:block 두 벌로 복붙되어 있었음). */
function ProgressHeadline({
  size,
  currentProgressPct,
  goalAmountDisplay,
  goalGapAmount,
  hasData,
}: Omit<OutlookProps, "timeline"> & { size: "sm" | "lg" }) {
  return (
    <div>
      <p
        className={`text-xs text-gray-500 dark:text-gray-400 mb-0.5 ${size === "lg" ? "font-medium" : ""}`}
      >
        자산 목표 진행률
      </p>
      <p
        className={`font-bold text-gray-900 dark:text-gray-50 ${size === "lg" ? "text-lg" : "text-base"}`}
      >
        {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
      </p>
      {goalAmountDisplay != null && hasData && (
        <p className={`text-xs mt-0.5 text-gray-500 dark:text-gray-400`}>
          {goalGapAmount != null && goalGapAmount > 0
            ? `목표까지 ${fmtKrw(goalGapAmount)} 남음`
            : `목표 ${fmtKrw(goalAmountDisplay)} 달성`}
        </p>
      )}
    </div>
  );
}

function expectedDateLabel(timeline: GoalTimeline): string {
  if (timeline?.actual_expected_goal_date) return fmtMonth(timeline.actual_expected_goal_date);
  if (timeline?.expected_goal_date) return fmtMonth(timeline.expected_goal_date);
  return "—";
}

function hasOutlook({ timeline, currentProgressPct }: OutlookProps): boolean {
  return currentProgressPct != null || timeline != null;
}

/** 모바일 DCA 달성 전망 — 헤드라인(진행률+금액)은 항상 맨 위, 예상일/배지/진행바는 접기 뒤로 */
export function MobileDcaOutlook({
  detailOpen,
  onToggleDetail,
  ...props
}: OutlookProps & { detailOpen: boolean; onToggleDetail: () => void }) {
  const { timeline, currentProgressPct } = props;
  return (
    <div className="sm:hidden order-1 pb-1.5 mb-1.5 border-b border-gray-100 dark:border-gray-700">
      {hasOutlook(props) ? (
        <>
          <ProgressHeadline size="sm" {...props} />
          <CollapsibleSection
            isOpen={detailOpen}
            onToggle={onToggleDetail}
            label="달성 예상일 · 진행 상세"
            buttonClassName={`mt-1 w-full flex items-center justify-between ${TOUCH_HEIGHT_MIN} text-xs text-gray-500 dark:text-gray-400 font-medium`}
          >
            <div className="flex items-end justify-between">
              <p className="text-xs text-gray-400 dark:text-gray-500">실제 달성 예상</p>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                {expectedDateLabel(timeline)}
              </p>
            </div>
            <div className="flex items-center justify-between mt-1">
              {timeline?.lead_lag_months != null && timeline.lead_lag_months !== 0 ? (
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold ${
                    timeline.lead_lag_months > 0
                      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400"
                      : "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400"
                  }`}
                >
                  {timeline.lead_lag_months > 0 ? (
                    <>
                      <TrendingUp size={10} />
                      {timeline.lead_lag_months}개월 앞서
                    </>
                  ) : (
                    <>
                      <TrendingDown size={10} />
                      {Math.abs(timeline.lead_lag_months)}개월 지연
                    </>
                  )}
                </span>
              ) : (
                <span />
              )}
              {timeline?.expected_goal_date &&
                timeline?.lead_lag_months != null &&
                timeline.lead_lag_months !== 0 && (
                  <span className="text-xs text-gray-400 dark:text-gray-500">
                    계획: {fmtMonth(timeline.expected_goal_date)}
                  </span>
                )}
            </div>
            <div className="h-2.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden mt-1">
              <div
                className="h-full bg-blue-500 rounded-full transition-all"
                style={{ width: `${Math.min(currentProgressPct ?? 0, 100)}%` }}
              />
            </div>
          </CollapsibleSection>
        </>
      ) : (
        <Link
          to="/invest-plan"
          className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
        >
          DCA 투자 계획 설정하기 →
        </Link>
      )}
    </div>
  );
}

/** 데스크탑 DCA 달성 전망 — 부각 PRIMARY */
export function DesktopDcaOutlook(props: OutlookProps) {
  const { timeline, currentProgressPct } = props;
  if (!hasOutlook(props)) {
    return (
      <div className="hidden sm:block border-t border-gray-100 dark:border-gray-700 pt-4 mt-3">
        <Link
          to="/invest-plan"
          className="flex items-center gap-1.5 text-xs text-blue-600 dark:text-blue-400 hover:underline"
        >
          DCA 투자 계획 설정하기 <ArrowRight size={12} />
        </Link>
      </div>
    );
  }
  return (
    <div className="hidden sm:block border-t border-gray-100 dark:border-gray-700 pt-2 mt-2 space-y-2">
      <div className="grid grid-cols-3 gap-3">
        <ProgressHeadline size="lg" {...props} />
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">
            실제 달성 예상
          </p>
          <p className="text-base font-semibold text-blue-600 dark:text-blue-400">
            {expectedDateLabel(timeline)}
          </p>
          {timeline?.months_to_goal != null && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              약 {timeline.months_to_goal}개월 후
            </p>
          )}
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-0.5">계획 대비</p>
          {timeline?.lead_lag_months == null ? (
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">—</p>
          ) : timeline.lead_lag_months > 0 ? (
            <div className="mt-0.5 flex flex-col gap-1">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400 w-fit">
                <TrendingUp size={11} />
                {timeline.lead_lag_months}개월 앞서
              </span>
              {timeline.expected_goal_date && (
                <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                  계획 기준: {fmtMonth(timeline.expected_goal_date)}
                </span>
              )}
            </div>
          ) : timeline.lead_lag_months < 0 ? (
            <div className="mt-0.5 flex flex-col gap-1">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400 w-fit">
                <TrendingDown size={11} />
                {Math.abs(timeline.lead_lag_months)}개월 지연
              </span>
              {timeline.expected_goal_date && (
                <span className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                  계획 기준: {fmtMonth(timeline.expected_goal_date)}
                </span>
              )}
            </div>
          ) : (
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mt-1">계획과 일치</p>
          )}
        </div>
      </div>
      <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-blue-500 rounded-full transition-all"
          style={{ width: `${Math.min(currentProgressPct ?? 0, 100)}%` }}
        />
      </div>
    </div>
  );
}
