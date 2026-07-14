import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

interface Props {
  isOpen: boolean;
  onToggle: () => void;
  label: ReactNode;
  collapsedHint?: ReactNode;
  children: ReactNode;
  buttonClassName?: string;
}

/** 카드 내부에 삽입하는 경량 접기/펼치기 토글. 카드 전체를 감싸려면 CollapsibleCard 사용. */
export default function CollapsibleSection({
  isOpen,
  onToggle,
  label,
  collapsedHint,
  children,
  buttonClassName = "w-full flex items-center justify-between py-2 px-3 text-xs text-gray-400 dark:text-gray-500 font-medium hover:bg-gray-50 dark:hover:bg-gray-800 rounded-lg transition-colors",
}: Props) {
  return (
    <div>
      <button onClick={onToggle} className={buttonClassName} aria-expanded={isOpen}>
        <span>{label}</span>
        <ChevronDown
          size={16}
          className={`transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>
      {!isOpen && collapsedHint && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 px-3">{collapsedHint}</p>
      )}
      {isOpen && <div className="mt-2">{children}</div>}
    </div>
  );
}
