export const TOUCH_TARGET_MIN = "min-h-[44px] min-w-[44px] flex items-center justify-center";
export const TOUCH_TARGET_MIN_MOBILE_ONLY =
  "min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center";
export const TOUCH_TARGET_ROW = "min-h-[44px] min-w-[44px] flex items-center justify-start";
/** 배지/탭/필터 칩처럼 조밀하게 나열되는 보조 요소용 절충 터치 타겟(36px, WCAG AA 24px 이상 + 컴팩트한 칩 톤 유지).
 * 단독으로 배치되는 명확한 액션 버튼(수정/삭제/닫기 등)에는 TOUCH_TARGET_MIN_MOBILE_ONLY(44px)를 우선 사용. */
export const TOUCH_TARGET_COMPACT_MOBILE_ONLY =
  "min-h-9 min-w-9 sm:min-h-0 sm:min-w-0 flex items-center justify-center";
