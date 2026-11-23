import type { MarketRiskLevel } from "@/api/marketSignals";
import { MARKET_SIGNAL_BADGE_CLASS, MARKET_SIGNAL_LABEL } from "@/utils/marketSignalBadge";

interface Props {
  level: MarketRiskLevel;
  size?: "xs" | "sm";
}

// 라벨·색은 홈 "지금 할 일" 알약과 같은 정의(`utils/marketSignalBadge`)를 쓴다 — 예전엔 두 곳이 각자 들고 있었다(plans/150 B3)
const BORDER_CLASS: Record<MarketRiskLevel, string> = {
  GREEN: "border-green-300 dark:border-green-700/30",
  YELLOW: "border-yellow-300 dark:border-yellow-700/30",
  RED: "border-red-300 dark:border-red-700/30",
};

const ICON: Record<MarketRiskLevel, string> = {
  GREEN: "🟢",
  YELLOW: "🟡",
  RED: "🔴",
};

export default function MarketSignalLevelBadge({ level, size = "xs" }: Props) {
  const label = MARKET_SIGNAL_LABEL[level];
  const cls = `${MARKET_SIGNAL_BADGE_CLASS[level]} ${BORDER_CLASS[level]}`;
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
