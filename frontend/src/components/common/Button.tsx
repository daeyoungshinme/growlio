import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "ghost" | "outline";
type Size = "sm" | "md";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-blue-600 text-white hover:bg-blue-700",
  secondary:
    "border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800",
  danger:
    "border border-red-300 text-red-600 hover:bg-red-50",
  ghost:
    "text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950",
  outline:
    "border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-5 py-2 text-sm font-medium",
};

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  icon,
  children,
  disabled,
  className,
  ...rest
}: Props) {
  return (
    <button
      disabled={disabled || loading}
      className={[
        "inline-flex items-center gap-1.5 rounded-lg transition-colors",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className ?? "",
      ].join(" ")}
      {...rest}
    >
      {loading ? <Loader2 size={14} className="animate-spin" /> : icon}
      {children}
    </button>
  );
}
