import { describe, it, expect } from "vitest";
import { shrinkAllocations } from "@/utils/dipBuyAllocation";

describe("shrinkAllocations — 백엔드 dip_buy_calculator.shrink_allocations와 같은 규칙", () => {
  it.each([
    [[60], 40, [60]],
    [[100], 50, [50]],
    [[60, 40], 50, [30, 20]],
    [[100], 99, [1]],
    [[100], 100, null],
    [[50, 50], 99, null],
  ])("%j + 새 %d%% → %j", (others, next, expected) => {
    expect(shrinkAllocations(others, next)).toEqual(expected);
  });
});
