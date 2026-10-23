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

/** 차트 축 글자 크기 — 앱 전역 최소 12px 규칙(docs/plans/67). 11·10px이 차트에만 남아 있었다. */
export const CHART_TICK_FONT_SIZE = 12;

/** 다크모드 대응 Recharts 축 tick 스타일 */
export function chartTickStyle(isDark: boolean) {
  return { fontSize: CHART_TICK_FONT_SIZE, fill: isDark ? "#9CA3AF" : "#6B7280" };
}
