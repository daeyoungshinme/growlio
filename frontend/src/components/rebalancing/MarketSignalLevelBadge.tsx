import type { MarketRiskLevel } from "@/api/marketSignals";

interface Props {
  level: MarketRiskLevel;
  size?: "xs" | "sm";
}

const LEVEL_CONFIG: Record<MarketRiskLevel, { label: string; cls: string }> = {
  GREEN: {
    label: "안전",
    cls: "bg-green-100 text-green-700 border-green-300 dark:bg-green-900/30 dark:text-green-400 dark:border-green-700/30",
  },
  YELLOW: {
    label: "주의",
    cls: "bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-700/30",
  },
  RED: {
    label: "위험",
    cls: "bg-red-100 text-red-700 border-red-300 dark:bg-red-900/30 dark:text-red-400 dark:border-red-700/30",
  },
};

const ICON: Record<MarketRiskLevel, string> = {
  GREEN: "🟢",
  YELLOW: "🟡",
  RED: "🔴",
};

export default function MarketSignalLevelBadge({ level, size = "xs" }: Props) {
  const { label, cls } = LEVEL_CONFIG[level];
  const textSize = size === "xs" ? "text-xs" : "text-sm";
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border font-medium ${textSize} ${cls}`}
    >
      <span>{ICON[level]}</span>
      <span>{label}</span>
    </span>
  );
}
