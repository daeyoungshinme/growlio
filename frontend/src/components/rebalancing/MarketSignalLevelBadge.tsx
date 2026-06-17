import type { MarketRiskLevel } from "@/api/marketSignals";

interface Props {
  level: MarketRiskLevel;
  size?: "xs" | "sm";
}

const LEVEL_CONFIG: Record<MarketRiskLevel, { label: string; cls: string }> = {
  GREEN: { label: "안전", cls: "bg-green-900/30 text-green-400 border-green-700/30" },
  YELLOW: { label: "주의", cls: "bg-yellow-900/30 text-yellow-400 border-yellow-700/30" },
  RED: { label: "위험", cls: "bg-red-900/30 text-red-400 border-red-700/30" },
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
