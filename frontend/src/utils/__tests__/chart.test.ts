import { describe, it, expect } from "vitest";
import { chartTooltipStyle } from "../chart";

describe("chartTooltipStyle", () => {
  it("라이트 모드 스타일 반환", () => {
    const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(false);
    expect(contentStyle.backgroundColor).toBe("#ffffff");
    expect(contentStyle.color).toBe("#111827");
    expect(labelStyle.color).toBe("#111827");
    expect(itemStyle.color).toBe("#111827");
    expect(contentStyle.border).toContain("#E5E7EB");
  });

  it("다크 모드 스타일 반환", () => {
    const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(true);
    expect(contentStyle.backgroundColor).toBe("#1f2937");
    expect(contentStyle.color).toBe("#f9fafb");
    expect(labelStyle.color).toBe("#f9fafb");
    expect(itemStyle.color).toBe("#f9fafb");
    expect(contentStyle.border).toContain("#374151");
  });

  it("폰트 크기 및 borderRadius 포함", () => {
    const { contentStyle } = chartTooltipStyle(false);
    expect(contentStyle.fontSize).toBe(12);
    expect(contentStyle.borderRadius).toBe(8);
  });

  it("라이트/다크 결과가 다름", () => {
    const light = chartTooltipStyle(false);
    const dark = chartTooltipStyle(true);
    expect(light.contentStyle.backgroundColor).not.toBe(dark.contentStyle.backgroundColor);
  });
});
