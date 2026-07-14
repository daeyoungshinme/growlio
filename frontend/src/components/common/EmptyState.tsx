import type { ComponentType } from "react";

interface Props {
  icon?: ComponentType<{ size?: number; className?: string }>;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  compact?: boolean;
  className?: string;
}

export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  compact,
  className,
}: Props) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center px-4 ${compact ? "py-6" : "py-12"} ${className ?? ""}`}
    >
      {Icon && <Icon size={40} className="mb-3 text-gray-300 dark:text-gray-600" />}
      <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
      {description && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{description}</p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-3 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
