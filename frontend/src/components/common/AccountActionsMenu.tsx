import { useEffect, useRef, useState } from "react";
import { MoreVertical } from "lucide-react";
import { TOUCH_TARGET_MIN_MOBILE_ONLY, TOUCH_TARGET_ROW } from "@/constants/uiSizes";

export interface AccountActionsMenuItem {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: "default" | "danger";
}

interface Props {
  items: AccountActionsMenuItem[];
  /** 트리거 버튼 aria-label. 기본값 "더 보기". */
  ariaLabel?: string;
}

/** 카드 헤더 등에 밀집된 부가 액션들을 `⋯` 메뉴로 접는 공용 컴포넌트.
 * 아이콘+라벨 텍스트를 함께 렌더해 모바일에서 `title` 툴팁이 뜨지 않는 문제를 우회한다. */
export default function AccountActionsMenu({ items, ariaLabel = "더 보기" }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    function handlePointerDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setIsOpen(false);
    }
    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setIsOpen((v) => !v)}
        aria-label={ariaLabel}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors`}
      >
        <MoreVertical size={16} />
      </button>
      {isOpen && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-1 w-44 py-1 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg z-20"
        >
          {items.map((item, i) => (
            <button
              key={i}
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setIsOpen(false);
                item.onClick();
              }}
              className={`w-full gap-2.5 px-3 text-sm transition-colors disabled:opacity-50 ${TOUCH_TARGET_ROW} ${
                item.variant === "danger"
                  ? "text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950"
                  : "text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
              }`}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
