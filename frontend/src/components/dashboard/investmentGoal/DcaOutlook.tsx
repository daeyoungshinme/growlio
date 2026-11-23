import { fmtKrw, fmtMonth } from "@/utils/format";
import type { DCAAnalysisData } from "@/api/invest";

type GoalTimeline = DCAAnalysisData["goal_timeline"] | undefined;

interface OutlookProps {
  timeline: GoalTimeline;
  currentProgressPct: number | null | undefined;
  goalAmountDisplay: number | null | undefined;
  goalGapAmount: number | null;
  hasData: boolean;
}

/** 실적 기준 예상월 우선, 없으면 계획 기준 */
function expectedMonth(timeline: GoalTimeline): string | null {
  const ymd = timeline?.actual_expected_goal_date ?? timeline?.expected_goal_date;
  return ymd ? fmtMonth(ymd) : null;
}

/**
 * 자산 목표 전망 — 홈은 진행률·남은 금액·예상월 한 줄만. 계획 대비 앞섬/지연·진행 막대·연/월 달성표는
 * 계획 › 적립 계획 `GoalTimelineCard`가 주인이라 여기서 반복하지 않는다(plans/150 B1 — 예전 접힘 상세가 거의 같은 내용).
 * 이동은 카드 헤더 링크 하나로.
 */
export function DcaOutlook({
  timeline,
  currentProgressPct,
  goalAmountDisplay,
  goalGapAmount,
  hasData,
}: OutlookProps) {
  if (currentProgressPct == null && timeline == null) {
    return (
      <p className="order-1 pb-1.5 mb-1.5 border-b border-gray-100 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
        자산 목표를 정하면 진행률과 달성 예상 시점이 보여요
      </p>
    );
  }
  const month = expectedMonth(timeline);
  const gapText =
    goalAmountDisplay != null && hasData && goalGapAmount != null
      ? goalGapAmount > 0
        ? `목표까지 ${fmtKrw(goalGapAmount)} 남음`
        : `목표 ${fmtKrw(goalAmountDisplay)} 달성`
      : null;
  const subParts = [
    gapText,
    month && goalGapAmount != null && goalGapAmount > 0 ? `${month} 달성 예상` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="order-1 pb-1.5 mb-1.5 border-b border-gray-100 dark:border-gray-700">
      <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5">자산 목표 진행률</p>
      <p className="text-base font-bold text-gray-900 dark:text-gray-50">
        {currentProgressPct != null ? `${currentProgressPct.toFixed(1)}%` : "—"}
      </p>
      {subParts && <p className="text-xs mt-0.5 text-gray-500 dark:text-gray-400">{subParts}</p>}
    </div>
  );
}
