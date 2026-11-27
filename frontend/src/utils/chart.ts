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

/** 누적 막대 툴팁 payload의 값 합계 — 숫자가 아닌 값은 0으로 본다 */
export function stackedTotal(payload: readonly { value?: unknown }[] | undefined): number {
  return (payload ?? []).reduce((sum, item) => {
    const v = Number(item.value);
    return sum + (Number.isFinite(v) ? v : 0);
  }, 0);
}

/**
 * recharts 3 `Legend`는 기본으로 라벨 이름순 정렬(`itemSorter="value"`) — 시리즈를 그리는 순서(쌓기 순서)대로 두려면
 * 이 정렬 함수를 넘긴다. `null`(정렬 안 함)은 렌더마다 순서가 바뀔 수 있다고 문서가 경고한다.
 */
export function legendOrder(keys: readonly string[]): (item: { dataKey?: unknown }) => number {
  return (item) => {
    const idx = keys.indexOf(String(item.dataKey));
    return idx === -1 ? keys.length : idx;
  };
}
