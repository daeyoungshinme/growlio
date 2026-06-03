import { forwardRef, type InputHTMLAttributes } from "react";

interface FormInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  prefix?: string;
  suffix?: string;
  inputSize?: "sm" | "md";
}

/**
 * 공통 폼 입력 필드 — 다크모드 스타일 통합.
 * 추가 className을 통해 width 등 레이아웃 속성 전달.
 */
const FormInput = forwardRef<HTMLInputElement, FormInputProps>(
  ({ label, hint, prefix, suffix, inputSize = "md", className = "", ...props }, ref) => {
    const sizeClass = inputSize === "sm"
      ? "px-2 py-1.5 text-xs"
      : "px-3 py-3 text-sm";
    const baseClass =
      `border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 ` +
      `text-gray-900 dark:text-gray-50 rounded-lg ${sizeClass} ` +
      `focus:outline-none focus:ring-2 focus:ring-blue-500`;

    const input = (
      <input
        ref={ref}
        className={`${baseClass} ${prefix || suffix ? "flex-1 rounded-none first:rounded-l-lg last:rounded-r-lg" : "w-full"} ${className}`}
        {...props}
      />
    );

    if (!label && !prefix && !suffix && !hint) return input;

    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label className="text-xs text-gray-500 dark:text-gray-400">{label}</label>
        )}
        {prefix || suffix ? (
          <div className="flex items-center border border-gray-300 dark:border-gray-600 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
            {prefix && (
              <span className="px-2 text-sm text-gray-400 dark:text-gray-500 border-r border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700">
                {prefix}
              </span>
            )}
            <input
              ref={ref}
              className={`flex-1 bg-transparent ${sizeClass} text-gray-900 dark:text-gray-50 focus:outline-none ${className}`}
              {...props}
            />
            {suffix && (
              <span className="px-2 text-sm text-gray-400 dark:text-gray-500 border-l border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700">
                {suffix}
              </span>
            )}
          </div>
        ) : (
          input
        )}
        {hint && (
          <p className="text-xs text-gray-400 dark:text-gray-500">{hint}</p>
        )}
      </div>
    );
  }
);

FormInput.displayName = "FormInput";
export default FormInput;
