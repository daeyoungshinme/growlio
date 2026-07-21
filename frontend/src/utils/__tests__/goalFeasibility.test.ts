import { describe, expect, it } from "vitest";
import { classifyGoalFeasibility } from "@/utils/goalFeasibility";

describe("classifyGoalFeasibility", () => {
  it("returns the impossible band when required return is null", () => {
    const band = classifyGoalFeasibility(null);
    expect(band.label).toBe("매우 어려운 목표");
  });

  it("returns the stable band for low required returns", () => {
    expect(classifyGoalFeasibility(3).label).toBe("안정적인 목표");
    expect(classifyGoalFeasibility(6).label).toBe("안정적인 목표");
  });

  it("returns the challenging band for mid required returns", () => {
    expect(classifyGoalFeasibility(6.1).label).toBe("도전적인 목표");
    expect(classifyGoalFeasibility(12).label).toBe("도전적인 목표");
  });

  it("returns the aggressive band for high required returns", () => {
    expect(classifyGoalFeasibility(12.1).label).toBe("매우 공격적인 목표");
    expect(classifyGoalFeasibility(50).label).toBe("매우 공격적인 목표");
  });
});
