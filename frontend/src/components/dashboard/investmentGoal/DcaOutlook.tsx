import { Link } from "react-router-dom";
import { TrendingDown, TrendingUp } from "lucide-react";
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

function ProgressHeadline({
  currentProgressPct,
  goalAmountDisplay,
  goalGapAmount,
  hasData,
}: Omit<OutlookProps, "timeline">) {
  return (
    <div>
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">자산 목표 진행률</p>
      <p className="text-base font-bold text-gray-900 dark:text-gray-50">
        {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
      </p>
      {goalAmountDisplay != null && hasData && goalGapAmount != null && (
        <p className="text-xs mt-0.5 text-gray-500 dark:text-gray-400">
          {goalGapAmount > 0
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

/** 실적 기준 예상일이 없으면 계획 기준 날짜를 보여 주므로 라벨도 그에 맞춘다 */
function expectedDateCaption(timeline: GoalTimeline): string {
  return timeline?.actual_expected_goal_date ? "실제 기준 달성 예상" : "계획 기준 달성 예상";
}

function hasOutlook({ timeline, currentProgressPct }: OutlookProps): boolean {
  return currentProgressPct != null || timeline != null;
}

/** DCA 달성 전망 — 헤드라인(진행률+금액)은 항상 맨 위, 예상일/배지/진행바는 접기 뒤로. 상세 3칸은 계획 탭 */
export function DcaOutlook({
  detailOpen,
  onToggleDetail,
  ...props
}: OutlookProps & { detailOpen: boolean; onToggleDetail: () => void }) {
  const { timeline, currentProgressPct } = props;
  return (
    <div className="order-1 pb-1.5 mb-1.5 border-b border-gray-100 dark:border-gray-700">
      {hasOutlook(props) ? (
        <>
          <ProgressHeadline {...props} />
          <CollapsibleSection
            isOpen={detailOpen}
            onToggle={onToggleDetail}
            label="달성 예상일 · 진행 상세"
            buttonClassName={`mt-1 w-full flex items-center justify-between ${TOUCH_HEIGHT_MIN} text-xs text-gray-500 dark:text-gray-400 font-medium`}
          >
            <div className="flex items-end justify-between">
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {expectedDateCaption(timeline)}
              </p>
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
