import { TOUCH_HEIGHT_MIN } from "./uiSizes";

const BASE =
  "border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 " +
  "text-gray-900 dark:text-gray-50 rounded-lg " +
  "focus:outline-none focus:ring-2 focus:ring-blue-500";

export const INPUT_SM = BASE + ` px-3 py-2 text-sm ${TOUCH_HEIGHT_MIN}`;
export const INPUT_MD = BASE + ` px-3 py-2.5 text-base ${TOUCH_HEIGHT_MIN}`;
export const LABEL_SM = "text-xs text-gray-500 dark:text-gray-400";
export const LABEL_MD = "text-sm font-medium text-gray-700 dark:text-gray-300";
/** 라벨 아래 폭을 꽉 채우는 입력(설정·알림 폼) */
export const FORM_INPUT_SM = `mt-1 w-full ${INPUT_SM}`;
export const SELECT_SM = INPUT_SM;
export const TEXTAREA_SM = INPUT_SM + " resize-none";

export const FORM_LABEL = `block ${LABEL_MD} mb-1`;
