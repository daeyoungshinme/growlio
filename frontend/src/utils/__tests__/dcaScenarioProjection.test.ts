import { describe, it, expect } from "vitest";
import { projectedValueAtMonth, buildScenarioCurve } from "../dcaScenarioProjection";
import type { DCAProjectionPoint } from "@/api/invest";

describe("projectedValueAtMonth", () => {
  it("n=0이면 초기값 그대로 반환", () => {
    expect(projectedValueAtMonth(10_000_000, 500_000, 7, 0)).toBe(10_000_000);
  });

  it("r=0(수익률 0%)이면 원금 단순 합산", () => {
    expect(projectedValueAtMonth(10_000_000, 500_000, 0, 12)).toBe(10_000_000 + 500_000 * 12);
  });

  it("양수 r이면 백엔드 공식과 동일한 복리 계산", () => {
    const initial = 10_000_000;
    const pmt = 500_000;
    const annualReturnPct = 7;
    const n = 12;
    const r = annualReturnPct / 100 / 12;
    const expected = initial * Math.pow(1 + r, n) + pmt * ((Math.pow(1 + r, n) - 1) / r);
    expect(projectedValueAtMonth(initial, pmt, annualReturnPct, n)).toBeCloseTo(expected, 6);
  });

  it("수익률이 높을수록 같은 개월수에서 더 큰 값", () => {
    const conservative = projectedValueAtMonth(10_000_000, 500_000, 4, 24);
    const aggressive = projectedValueAtMonth(10_000_000, 500_000, 10, 24);
    expect(aggressive).toBeGreaterThan(conservative);
  });
});

describe("buildScenarioCurve", () => {
  const makePoint = (month: string, projected_krw: number): DCAProjectionPoint => ({
    month,
    projected_krw,
    actual_krw: null,
    achievement_pct: null,
    has_data: false,
  });

  it("빈 배열이면 빈 맵 반환", () => {
    expect(buildScenarioCurve([], 500_000, 7)).toEqual({});
  });

  it("month를 key로 하는 맵 생성, n=0 지점은 원래 초기값과 동일", () => {
    const points = [
      makePoint("2026-01", 10_000_000),
      makePoint("2026-02", 10_500_000),
      makePoint("2026-03", 11_000_000),
    ];
    const curve = buildScenarioCurve(points, 500_000, 7);
    expect(Object.keys(curve)).toEqual(["2026-01", "2026-02", "2026-03"]);
    expect(curve["2026-01"]).toBe(10_000_000);
    expect(curve["2026-03"]).toBe(projectedValueAtMonth(10_000_000, 500_000, 7, 2));
  });
});
