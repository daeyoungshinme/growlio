import { useCallback, useEffect, useRef, useState } from "react";
import { TOUCH_TARGET_MIN } from "@/constants/uiSizes";

type Variant = "underline" | "pill";

const END_FADE_STYLE = {
  maskImage: "linear-gradient(to right, black calc(100% - 24px), transparent)",
  WebkitMaskImage: "linear-gradient(to right, black calc(100% - 24px), transparent)",
};

/** 가로 스크롤 탭 오른쪽에 더 있는데 끝까지 안 밀었으면 true — 모바일에서 뒤쪽 탭이 있다는 힌트 */
function useHasMoreToRight() {
  const ref = useRef<HTMLDivElement>(null);
  const [hasMore, setHasMore] = useState(false);
  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setHasMore(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);
  useEffect(() => {
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [update]);
  return { ref, hasMore, update };
}

interface Props<T extends string> {
  tabs: readonly T[];
  activeTab: T;
  onChange: (tab: T) => void;
  variant?: Variant;
  className?: string;
  /** pill 변형 전용 — 버튼을 균등폭(모바일에서 flex-1)으로 채운다. 탭 2~3개짜리 세그먼트 컨트롤에 사용. */
  fullWidth?: boolean;
}

export default function Tabs<T extends string>({
  tabs,
  activeTab,
  onChange,
  variant = "underline",
  className,
  fullWidth,
}: Props<T>) {
  const { ref: scrollRef, hasMore, update: updateFade } = useHasMoreToRight();

  if (variant === "pill") {
    return (
      <div
        role="tablist"
        className={`flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 overflow-x-auto scrollbar-none [scroll-snap-type:x_mandatory] ${fullWidth ? "w-full sm:w-fit" : ""} ${className ?? ""}`}
      >
        {tabs.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            tabIndex={activeTab === tab ? 0 : -1}
            onClick={() => onChange(tab)}
            className={[
              "px-3 sm:px-5 py-2.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap [scroll-snap-align:start]",
              fullWidth ? "flex-1 sm:flex-none" : "shrink-0",
              TOUCH_TARGET_MIN,
              activeTab === tab
                ? "bg-white dark:bg-gray-700 shadow text-gray-900 dark:text-gray-50"
                : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200",
            ].join(" ")}
          >
            {tab}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      onScroll={updateFade}
      style={hasMore ? END_FADE_STYLE : undefined}
      role="tablist"
      className={`flex gap-1 border-b border-gray-200 dark:border-gray-700 overflow-x-auto scrollbar-none ${className ?? ""}`}
    >
      {tabs.map((tab) => (
        <button
          key={tab}
          role="tab"
          aria-selected={activeTab === tab}
          tabIndex={activeTab === tab ? 0 : -1}
          onClick={() => onChange(tab)}
          className={[
            "px-4 py-2 text-sm transition-colors border-b-2 -mb-px whitespace-nowrap shrink-0",
            TOUCH_TARGET_MIN,
            activeTab === tab
              ? "border-blue-600 text-blue-600 dark:text-blue-400 font-semibold dark:border-blue-400"
              : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300",
          ].join(" ")}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}
