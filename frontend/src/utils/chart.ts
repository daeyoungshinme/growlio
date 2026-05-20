import type { CSSProperties } from "react";

export interface ChartTooltipStyle {
  contentStyle: CSSProperties;
  labelStyle: CSSProperties;
  itemStyle: CSSProperties;
}

/** 다크모드 대응 Recharts Tooltip 스타일을 반환한다. */
export function chartTooltipStyle(isDark: boolean): ChartTooltipStyle {
  const color = isDark ? "#f9fafb" : "#111827";
  return {
    contentStyle: {
      fontSize: 12,
      borderRadius: 8,
      border: `1px solid ${isDark ? "#374151" : "#E5E7EB"}`,
      backgroundColor: isDark ? "#1f2937" : "#ffffff",
      color,
    },
    labelStyle: { color },
    itemStyle: { color },
  };
}
