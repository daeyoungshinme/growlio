import { describe, it, expect } from "vitest";
import { projectDividendGoal } from "../dividendGoalTimeline";

describe("projectDividendGoal", () => {
  it("이미 달성했으면 0개월", () => {
    expect(projectDividendGoal(100_000_000, 4_000_000, 3_000_000, 0)).toEqual({
      months: 0,
      yieldPct: 4,
    });
  });

  it("적립액이 클수록 일찍 닿는다", () => {
    const slow = projectDividendGoal(100_000_000, 3_000_000, 6_000_000, 500_000)!;
    const fast = projectDividendGoal(100_000_000, 3_000_000, 6_000_000, 2_000_000)!;
    expect(fast.months!).toBeLessThan(slow.months!);
  });

  it("적립 없이도 배당 재투자로 늘어난다", () => {
    const r = projectDividendGoal(100_000_000, 5_000_000, 6_000_000, null)!;
    // 연 5% 재투자(월복리)로 자산 1.2배 ≈ 44개월
    expect(r.months).toBeGreaterThan(40);
    expect(r.months).toBeLessThan(48);
  });

  it("배당이나 자산이 0이면 계산하지 않는다", () => {
    expect(projectDividendGoal(0, 1, 1, 1)).toBeNull();
    expect(projectDividendGoal(1_000, 0, 1, 1)).toBeNull();
  });

  it("50년 안에 못 닿으면 months null", () => {
    expect(projectDividendGoal(1_000_000, 1, 1_000_000_000, 0)?.months).toBeNull();
  });
});
