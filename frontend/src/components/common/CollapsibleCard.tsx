import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { ChevronDown } from "lucide-react";

interface Props {
  icon: LucideIcon;
  iconWrapClassName?: string;
  iconColorClassName?: string;
  title: ReactNode;
  titleBadge?: ReactNode;
  headerRight?: ReactNode;
  isOpen: boolean;
  onToggle: () => void;
  collapsedHint?: ReactNode;
  cardClassName?: string;
  children: ReactNode;
}

/** `.card` 전체를 감싸는 헤더+접기/펼치기 토글. isOpen/onToggle은 호출부에서 관리(controlled). */
export default function CollapsibleCard({
  icon: Icon,
  iconWrapClassName = "bg-gray-50 dark:bg-gray-800",
  iconColorClassName = "text-gray-500 dark:text-gray-400",
  title,
  titleBadge,
  headerRight,
  isOpen,
  onToggle,
  collapsedHint,
  cardClassName = "card",
  children,
}: Props) {
  return (
    <div className={cardClassName}>
      <div className="flex items-center justify-between">
        <button
          onClick={onToggle}
          className="flex items-center gap-2 min-w-0"
          aria-expanded={isOpen}
        >
          <div className={`p-1.5 rounded-lg shrink-0 ${iconWrapClassName}`}>
            <Icon size={16} className={iconColorClassName} />
          </div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-200">{title}</h2>
          {titleBadge}
          <ChevronDown
            size={14}
            className={`text-gray-500 shrink-0 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
        {headerRight && <div className="flex items-center gap-1.5 shrink-0">{headerRight}</div>}
      </div>
      {!isOpen && collapsedHint && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5 ml-0.5">{collapsedHint}</p>
      )}
      {isOpen && <div className="mt-3">{children}</div>}
    </div>
  );
}
