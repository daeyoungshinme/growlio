import { describe, it, expect } from "vitest";
import {
  buildLumpSumProjectionSeries,
  buildSavingsProjectionSeries,
  futureValueOfLumpSum,
  futureValueOfMonthlySavings,
} from "@/utils/savingsProjection";

describe("futureValueOfMonthlySavings", () => {
  it("수익률 0%면 단순 납입 누계와 같다", () => {
    expect(futureValueOfMonthlySavings(100_000, 0, 10)).toBe(100_000 * 12 * 10);
  });

  it("연 0년이면 0을 반환한다", () => {
    expect(futureValueOfMonthlySavings(100_000, 7, 0)).toBe(0);
  });

  it("월 10만원 x 연 7% x 10년의 복리 미래가치를 계산한다", () => {
    const fv = futureValueOfMonthlySavings(100_000, 7, 10);
    // 월복리 연금 공식 알려진 근사값 검증 (오차 허용 1%)
    expect(fv).toBeGreaterThan(17_000_000);
    expect(fv).toBeLessThan(17_500_000);
  });

  it("수익률이 높을수록 미래가치가 커진다", () => {
    const conservative = futureValueOfMonthlySavings(100_000, 4, 20);
    const aggressive = futureValueOfMonthlySavings(100_000, 10, 20);
    expect(aggressive).toBeGreaterThan(conservative);
  });
});

describe("buildSavingsProjectionSeries", () => {
  it("각 연도에 대해 원금 누계와 복리 미래가치를 함께 반환한다", () => {
    const series = buildSavingsProjectionSeries(50_000, 7, [1, 10]);
    expect(series).toHaveLength(2);
    expect(series[0]).toEqual({ year: 1, principal: 600_000, value: expect.any(Number) });
    expect(series[1].principal).toBe(50_000 * 12 * 10);
    // 복리 반영 시 원금보다 미래가치가 크다 (수익률 > 0)
    expect(series[1].value).toBeGreaterThan(series[1].principal);
  });

  it("기본 연도 배열(1/5/10/20/30)을 사용한다", () => {
    const series = buildSavingsProjectionSeries(100_000, 7);
    expect(series.map((p) => p.year)).toEqual([1, 5, 10, 20, 30]);
  });
});

describe("futureValueOfLumpSum", () => {
  it("수익률 0%면 원금 그대로 반환한다", () => {
    expect(futureValueOfLumpSum(3_000_000, 0, 10)).toBe(3_000_000);
  });

  it("연 0년이면 0을 반환한다", () => {
    expect(futureValueOfLumpSum(3_000_000, 7, 0)).toBe(0);
  });

  it("수익률이 높을수록 미래가치가 커진다", () => {
    const conservative = futureValueOfLumpSum(3_000_000, 4, 20);
    const aggressive = futureValueOfLumpSum(3_000_000, 10, 20);
    expect(aggressive).toBeGreaterThan(conservative);
  });
});

describe("buildLumpSumProjectionSeries", () => {
  it("각 연도의 principal은 항상 원금과 동일하고 value는 복리 반영되어 원금보다 크다", () => {
    const series = buildLumpSumProjectionSeries(3_000_000, 7, [1, 10]);
    expect(series).toHaveLength(2);
    expect(series[0].principal).toBe(3_000_000);
    expect(series[1].principal).toBe(3_000_000);
    expect(series[1].value).toBeGreaterThan(series[1].principal);
  });

  it("기본 연도 배열(1/5/10/20/30)을 사용한다", () => {
    const series = buildLumpSumProjectionSeries(3_000_000, 7);
    expect(series.map((p) => p.year)).toEqual([1, 5, 10, 20, 30]);
  });
});
