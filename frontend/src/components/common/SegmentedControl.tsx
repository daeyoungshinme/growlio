import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props<T extends string> {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (next: T) => void;
  ariaLabel: string;
  /** true면 가로 폭을 꽉 채우고 옵션을 균등 분할 (상단 탭용) */
  stretch?: boolean;
}

export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  ariaLabel,
  stretch = false,
}: Props<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`${stretch ? "flex w-full" : "inline-flex"} rounded-lg bg-gray-100 dark:bg-gray-800 p-0.5`}
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} ${stretch ? "flex-1 justify-center" : ""} px-3 text-xs rounded-md transition-colors ${
            value === opt.value
              ? "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 font-medium shadow-sm"
              : "text-gray-500 dark:text-gray-400"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
