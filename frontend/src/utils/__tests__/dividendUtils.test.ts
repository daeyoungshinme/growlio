import { describe, it, expect } from "vitest";
import { MONTH_LABELS, yieldBadgeClass, dividendFreqInfo, weightBarColor } from "../dividendUtils";

describe("MONTH_LABELS", () => {
  it("12개월 레이블 포함", () => {
    expect(MONTH_LABELS).toHaveLength(12);
    expect(MONTH_LABELS[0]).toBe("1월");
    expect(MONTH_LABELS[11]).toBe("12월");
  });
});

describe("yieldBadgeClass", () => {
  it("7% 이상이면 초록 bold 클래스", () => {
    const cls = yieldBadgeClass(7);
    expect(cls).toContain("green");
    expect(cls).toContain("font-bold");
  });

  it("7% 초과도 초록 bold 클래스", () => {
    const cls = yieldBadgeClass(10);
    expect(cls).toContain("green");
  });

  it("4% 이상 7% 미만이면 emerald 클래스", () => {
    const cls = yieldBadgeClass(5);
    expect(cls).toContain("emerald");
  });

  it("2% 이상 4% 미만이면 amber 클래스", () => {
    const cls = yieldBadgeClass(3);
    expect(cls).toContain("amber");
  });

  it("2% 미만이면 gray 클래스", () => {
    const cls = yieldBadgeClass(1);
    expect(cls).toContain("gray");
  });

  it("0%도 gray 클래스", () => {
    const cls = yieldBadgeClass(0);
    expect(cls).toContain("gray");
  });
});

describe("dividendFreqInfo", () => {
  it("빈 배열이면 미설정", () => {
    const { label } = dividendFreqInfo([], false);
    expect(label).toBe("미설정");
  });

  it("12개월이면 월배당", () => {
    const { label } = dividendFreqInfo([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], false);
    expect(label).toBe("월배당");
  });

  it("4개월이면 분기배당", () => {
    const { label } = dividendFreqInfo([3, 6, 9, 12], false);
    expect(label).toBe("분기배당");
  });

  it("2개월이면 반기배당", () => {
    const { label } = dividendFreqInfo([6, 12], false);
    expect(label).toBe("반기배당");
  });

  it("1개월이면 연배당", () => {
    const { label } = dividendFreqInfo([12], false);
    expect(label).toBe("연배당");
  });

  it("수동 입력이면 n회/년(수동)", () => {
    const { label } = dividendFreqInfo([1, 5, 9], true);
    expect(label).toBe("3회/년(수동)");
  });

  it("자동 비표준 횟수이면 n회/년", () => {
    const { label } = dividendFreqInfo([1, 5, 9], false);
    expect(label).toBe("3회/년");
  });

  it("결과에 cls 포함", () => {
    const { cls } = dividendFreqInfo([3, 6, 9, 12], false);
    expect(typeof cls).toBe("string");
    expect(cls.length).toBeGreaterThan(0);
  });
});

describe("weightBarColor", () => {
  it("25% 이상이면 amber", () => {
    expect(weightBarColor(25)).toContain("amber");
    expect(weightBarColor(30)).toContain("amber");
  });

  it("15% 이상 25% 미만이면 blue", () => {
    expect(weightBarColor(15)).toContain("blue");
    expect(weightBarColor(20)).toContain("blue");
  });

  it("5% 이상 15% 미만이면 emerald", () => {
    expect(weightBarColor(5)).toContain("emerald");
    expect(weightBarColor(10)).toContain("emerald");
  });

  it("5% 미만이면 gray", () => {
    expect(weightBarColor(4)).toContain("gray");
    expect(weightBarColor(0)).toContain("gray");
  });
});
