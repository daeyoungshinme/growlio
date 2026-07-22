import type { InputHTMLAttributes } from "react";
import { INPUT_SM, INPUT_MD, LABEL_SM, LABEL_MD } from "@/constants/inputStyles";

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, "size"> {
  label: string;
  hint?: string;
  error?: string;
  /** 입력 중인 값을 실시간으로 에코하는 프리뷰 문구 (예: 콤마 구분 금액). error 유무와 무관하게 항상 표시 */
  preview?: string;
  inputSize?: "sm" | "md";
}

export default function FormInput({
  label,
  hint,
  error,
  preview,
  inputSize = "sm",
  id,
  required,
  className,
  ...inputProps
}: Props) {
  const inputId = id ?? label.replace(/\s+/g, "-").toLowerCase();
  const baseClass = inputSize === "md" ? INPUT_MD : INPUT_SM;
  const labelClass = inputSize === "md" ? LABEL_MD : LABEL_SM;
  const errorClass = "border-red-400 dark:border-red-500 focus:ring-red-400";

  return (
    <div>
      <label htmlFor={inputId} className={`block mb-1 font-medium ${labelClass}`}>
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <input
        id={inputId}
        className={`w-full ${baseClass} ${error ? errorClass : ""} ${className ?? ""}`}
        required={required}
        {...inputProps}
      />
      {preview && (
        <p className="text-xs font-medium text-blue-600 dark:text-blue-400 mt-1">{preview}</p>
      )}
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
      {hint && !error && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{hint}</p>}
    </div>
  );
}
