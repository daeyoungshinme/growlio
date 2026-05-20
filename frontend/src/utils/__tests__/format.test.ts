import { describe, it, expect } from "vitest";
import { fmtKrw, fmtKrwNullable, fmtKrwShort, fmtMonth, fmtPct } from "../format";

describe("fmtKrw", () => {
  it("억원 단위 변환", () => {
    expect(fmtKrw(150_000_000)).toBe("1.50억원");
    expect(fmtKrw(100_000_000)).toBe("1.00억원");
  });

  it("만원 단위 변환", () => {
    expect(fmtKrw(50_000)).toBe("5만원");
    expect(fmtKrw(10_000)).toBe("1만원");
  });

  it("원 단위 변환", () => {
    expect(fmtKrw(3_000)).toBe("3,000원");
    expect(fmtKrw(0)).toBe("0원");
  });

  it("음수 처리", () => {
    expect(fmtKrw(-150_000_000)).toBe("-1.50억원");
    expect(fmtKrw(-50_000)).toBe("-5만원");
  });
});

describe("fmtKrwNullable", () => {
  it("null이면 대시 반환", () => {
    expect(fmtKrwNullable(null)).toBe("—");
    expect(fmtKrwNullable(undefined)).toBe("—");
  });

  it("숫자는 fmtKrw와 동일", () => {
    expect(fmtKrwNullable(50_000)).toBe("5만원");
  });
});

describe("fmtKrwShort", () => {
  it("억 단위 (원 없음)", () => {
    expect(fmtKrwShort(150_000_000)).toBe("1.5억");
  });

  it("만 단위 (원 없음)", () => {
    expect(fmtKrwShort(50_000)).toBe("5만");
  });
});

describe("fmtMonth", () => {
  it("YYYY-MM → YYYY년 M월 변환", () => {
    expect(fmtMonth("2025-05")).toBe("2025년 5월");
    expect(fmtMonth("2024-01")).toBe("2024년 1월");
    expect(fmtMonth("2024-12")).toBe("2024년 12월");
  });
});

describe("fmtPct", () => {
  it("양수에는 + 접두사", () => {
    expect(fmtPct(5.23)).toBe("+5.23%");
    expect(fmtPct(0)).toBe("+0.00%");
  });

  it("음수는 그대로", () => {
    expect(fmtPct(-3.1)).toBe("-3.10%");
  });

  it("null이면 대시 반환", () => {
    expect(fmtPct(null)).toBe("—");
  });

  it("digits 파라미터 적용", () => {
    expect(fmtPct(5.2345, 1)).toBe("+5.2%");
  });
});
