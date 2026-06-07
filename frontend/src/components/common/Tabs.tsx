type Variant = "underline" | "pill";

interface Props<T extends string> {
  tabs: readonly T[];
  activeTab: T;
  onChange: (tab: T) => void;
  variant?: Variant;
  className?: string;
}

export default function Tabs<T extends string>({
  tabs,
  activeTab,
  onChange,
  variant = "underline",
  className,
}: Props<T>) {
  if (variant === "pill") {
    return (
      <div
        className={`flex gap-1 bg-gray-100 dark:bg-gray-800 rounded-xl p-1 overflow-x-auto scrollbar-none ${className ?? ""}`}
      >
        {tabs.map((tab) => (
          <button
            key={tab}
            onClick={() => onChange(tab)}
            className={[
              "px-3 sm:px-5 py-2.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap shrink-0",
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
    <div className={`flex gap-1 border-b border-gray-200 dark:border-gray-700 ${className ?? ""}`}>
      {tabs.map((tab) => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={[
            "px-4 py-2 text-sm transition-colors border-b-2 -mb-px",
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
