import { describe, it, expect } from "vitest";
import { pnlColor, PROFIT_COLOR, LOSS_COLOR } from "@/utils/colors";

describe("pnlColor (한국 주식 관례)", () => {
  it("양수 수익 → 빨간색 (PROFIT_COLOR)", () => {
    expect(pnlColor(100)).toBe(PROFIT_COLOR);
    expect(pnlColor(0.01)).toBe(PROFIT_COLOR);
  });

  it("0은 수익으로 처리 (PROFIT_COLOR)", () => {
    expect(pnlColor(0)).toBe(PROFIT_COLOR);
  });

  it("음수 손실 → 파란색 (LOSS_COLOR)", () => {
    expect(pnlColor(-100)).toBe(LOSS_COLOR);
    expect(pnlColor(-0.01)).toBe(LOSS_COLOR);
  });

  it("한국 관례: 수익=red, 손실=blue (서양 반대)", () => {
    expect(PROFIT_COLOR).toContain("red");
    expect(LOSS_COLOR).toContain("blue");
  });
});
