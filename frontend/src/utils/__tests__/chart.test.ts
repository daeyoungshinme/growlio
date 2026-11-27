import { describe, it, expect } from "vitest";
import { chartTooltipStyle, legendOrder, stackedTotal } from "../chart";

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

describe("legendOrder", () => {
  it("recharts 3 기본(이름순) 대신 넘긴 시리즈 순서대로 정렬 값을 준다", () => {
    const sorter = legendOrder(["STOCK", "BANK", "PENSION"]);
    const items = [{ dataKey: "PENSION" }, { dataKey: "STOCK" }, { dataKey: "BANK" }];
    expect([...items].sort((a, b) => sorter(a) - sorter(b)).map((i) => i.dataKey)).toEqual([
      "STOCK",
      "BANK",
      "PENSION",
    ]);
    expect(sorter({ dataKey: "UNKNOWN" })).toBe(3); // 모르는 키는 맨 뒤
  });
});

describe("stackedTotal", () => {
  it("누적 막대 툴팁 항목 값을 합산한다", () => {
    expect(stackedTotal([{ value: 70_000_000 }, { value: 30_000_000 }])).toBe(100_000_000);
  });

  it("숫자가 아닌 값·빈 payload는 0으로 본다", () => {
    expect(stackedTotal([{ value: 10 }, { value: undefined }, { value: "x" }])).toBe(10);
    expect(stackedTotal(undefined)).toBe(0);
  });
});
