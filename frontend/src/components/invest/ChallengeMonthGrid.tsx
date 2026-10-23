import { useState } from "react";
import type { ChallengeMonth } from "@/api/challenges";
import { fmtKrwShort, fmtMonth } from "@/utils/format";
import { toast } from "@/utils/toast";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";

interface Props {
  months: ChallengeMonth[];
  hasTarget: boolean;
}

/** 처음 보여줄 최근 개월 수 — 긴 챌린지는 셀이 끝없이 이어져 카드가 길어졌다 (docs/plans/67) */
const RECENT_MONTHS = 12;

/** 적립 습관 캘린더 — 월별 달성 상태를 색칠된 셀 그리드로 표시. 셀을 탭하면 그 달 입금액을 알려준다
 * (예전엔 hover 전용 title이라 터치에선 금액을 볼 방법이 없었다). */
export default function ChallengeMonthGrid({ months, hasTarget }: Props) {
  const [showAll, setShowAll] = useState(false);
  if (months.length === 0) {
    return <p className="text-xs text-gray-500 dark:text-gray-400">아직 기록된 달이 없어요.</p>;
  }

  const visible = showAll ? months : months.slice(-RECENT_MONTHS);
  const hiddenCount = months.length - visible.length;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {visible.map((m, i) => {
          const met = hasTarget ? m.target_met : m.satisfied;
          const partial = hasTarget && m.satisfied && !m.target_met;
          const cls = met
            ? "bg-emerald-500 text-white"
            : partial
              ? "bg-amber-400 text-white"
              : "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400";
          const statusLabel = met ? "완료" : partial ? "일부 달성" : "미완료";
          const monthNum = Number(m.month.slice(5));
          // 연도가 바뀌는 칸(첫 칸·1월)에만 연도를 붙여 "1월"이 어느 해인지 구분
          const showYear = i === 0 || monthNum === 1;
          return (
            <button
              type="button"
              key={m.month}
              aria-label={`${fmtMonth(m.month)}, ${statusLabel}, ${fmtKrwShort(m.net_krw)}원`}
              onClick={() =>
                toast(`${fmtMonth(m.month)} · ${statusLabel} · ${fmtKrwShort(m.net_krw)}원`, "info")
              }
              className={`flex flex-col items-center justify-center rounded-md w-11 h-11 text-xs font-medium leading-tight ${cls}`}
            >
              <span>{showYear ? `'${m.month.slice(2, 4)}.${monthNum}` : `${monthNum}월`}</span>
              <span aria-hidden="true">{met ? "✓" : partial ? "•" : "—"}</span>
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> 완료
        </span>
        {hasTarget && (
          <span className="flex items-center gap-1">
            <span className="w-2.5 h-2.5 rounded-sm bg-amber-400" /> 일부 달성
          </span>
        )}
        <span className="flex items-center gap-1">
          <span className="w-2.5 h-2.5 rounded-sm bg-gray-200 dark:bg-gray-600" /> 미완료
        </span>
        <span>· 칸을 누르면 입금액</span>
        {hiddenCount > 0 && (
          <button
            type="button"
            onClick={() => setShowAll(true)}
            className={`${TOUCH_TARGET_ROW} ml-auto !min-w-0 font-medium text-blue-600 dark:text-blue-400`}
          >
            이전 {hiddenCount}개월 보기
          </button>
        )}
      </div>
    </div>
  );
}
