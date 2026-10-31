import type { ReactNode } from "react";

import { TOUCH_HEIGHT_MIN } from "@/constants/uiSizes";
interface ToggleSwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  ariaLabel?: string;
}

const SWITCH_TRACK_CLASS =
  "w-11 h-6 bg-gray-200 dark:bg-gray-700 peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:after:translate-x-full";

export function ToggleSwitch({ checked, onChange, disabled, ariaLabel }: ToggleSwitchProps) {
  return (
    <label
      className={`relative inline-flex items-center shrink-0 ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only peer"
        aria-label={ariaLabel}
      />
      <div className={SWITCH_TRACK_CLASS} />
    </label>
  );
}

interface ToggleRowProps extends Omit<ToggleSwitchProps, "ariaLabel"> {
  title: string;
  description?: ReactNode;
}

/** 제목·설명 + 스위치 한 행 — 행 전체가 label이라 어디를 눌러도 토글된다(24px 스위치만 눌리던 문제,
 * docs/plans/67). 접근성 이름은 제목만 쓴다(설명까지 읽히면 길어짐). */
export function ToggleRow({ title, description, checked, onChange, disabled }: ToggleRowProps) {
  return (
    <label
      className={`flex items-start justify-between gap-3 ${TOUCH_HEIGHT_MIN} py-1 ${disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"}`}
    >
      <span className="flex-1 min-w-0">
        <span className="block text-sm text-gray-700 dark:text-gray-300">{title}</span>
        {description && (
          <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {description}
          </span>
        )}
      </span>
      <span className="relative inline-flex items-center shrink-0 mt-0.5">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only peer"
          aria-label={title}
        />
        <span className={`block ${SWITCH_TRACK_CLASS}`} />
      </span>
    </label>
  );
}
