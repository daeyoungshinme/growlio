import { Link } from "react-router-dom";
import { clampPct } from "@/utils/format";
import { TOUCH_TARGET_MIN_MOBILE_ONLY, TOUCH_TARGET_ROW } from "@/constants/uiSizes";
import type { GoalChip } from "./goalChips";

interface Props {
  chips: GoalChip[];
  laggingKey: string | null;
  showAll: boolean;
  onToggleShowAll: () => void;
}

/** 목표 항목 — 데스크탑은 4개 항상 표시(미설정은 안내 CTA). 모바일은 가장 뒤처진 목표만 기본 노출 */
export default function GoalChipGrid({ chips, laggingKey, showAll, onToggleShowAll }: Props) {
  const hiddenOnMobileCount = chips.filter((c) => c.key !== laggingKey).length;
  // "모두 순항 중"은 설정한 목표가 있을 때만 — 미설정 칩까지 세면 목표가 없는데도 순항이라고 말하게 된다
  const hasAnySetChip = chips.some((c) => c.isSet);
  return (
    <>
      <div
        className={`order-2 sm:order-1 grid gap-px bg-gray-100 dark:bg-gray-700 ${
          showAll ? "grid-cols-2" : "grid-cols-1 sm:grid-cols-2"
        }`}
      >
        {chips.map((chip) => (
          <div
            key={chip.key}
            className={`min-w-0 bg-white dark:bg-gray-900 p-2 ${
              showAll || chip.key === laggingKey ? "" : "hidden sm:block"
            }`}
          >
            {chip.key === laggingKey && !showAll && (
              <p className="sm:hidden text-xs font-medium text-amber-600 dark:text-amber-400 mb-0.5">
                가장 뒤처진 목표
              </p>
            )}
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-0.5 truncate">{chip.label}</p>
            {chip.isSet ? (
              <>
                {chip.content}
                {chip.barPct != null && (
                  <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-1 mt-1">
                    <div
                      className={`h-full rounded-full ${chip.barColorClass}`}
                      style={{ width: `${clampPct(chip.barPct)}%` }}
                    />
                  </div>
                )}
              </>
            ) : (
              <>
                <p className="text-sm text-gray-300 dark:text-gray-600">미설정</p>
                <Link
                  to={chip.setupHref}
                  className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} text-xs text-blue-600 dark:text-blue-400 hover:underline`}
                >
                  설정하기
                </Link>
              </>
            )}
          </div>
        ))}
      </div>

      {hiddenOnMobileCount > 0 && (
        <button
          type="button"
          onClick={onToggleShowAll}
          aria-expanded={showAll}
          className={`sm:hidden order-3 ${TOUCH_TARGET_ROW} w-full justify-center text-xs font-medium text-gray-500 dark:text-gray-400`}
        >
          {showAll
            ? "접기"
            : laggingKey
              ? `목표 ${hiddenOnMobileCount}개 더 보기`
              : hasAnySetChip
                ? `설정한 목표 모두 순항 중 · 목표 ${hiddenOnMobileCount}개 보기`
                : `목표 ${hiddenOnMobileCount}개 보기`}
        </button>
      )}
    </>
  );
}
