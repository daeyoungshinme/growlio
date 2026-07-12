import { describe, it, expect } from "vitest";
import { recommendDriftThresholdPct } from "@/utils/rebalancingThresholdRecommendation";

describe("recommendDriftThresholdPct", () => {
  it("GENERAL + MID_TERM은 기본값 5.0을 반환한다", () => {
    expect(recommendDriftThresholdPct("GENERAL", "MID_TERM")).toBe(5.0);
  });

  it("과세이연 계좌(ISA/연금저축/IRP)는 임계값을 넓힌다", () => {
    expect(recommendDriftThresholdPct("ISA", "MID_TERM")).toBe(7.0);
    expect(recommendDriftThresholdPct("PENSION_SAVINGS", "MID_TERM")).toBe(7.0);
    expect(recommendDriftThresholdPct("IRP", "MID_TERM")).toBe(7.0);
  });

  it("해외전용 계좌는 과세이연 계좌보다는 좁게 넓힌다", () => {
    expect(recommendDriftThresholdPct("OVERSEAS_DEDICATED", "MID_TERM")).toBe(6.5);
  });

  it("단기는 좁히고 장기는 넓힌다", () => {
    expect(recommendDriftThresholdPct("GENERAL", "SHORT_TERM")).toBe(3.5);
    expect(recommendDriftThresholdPct("GENERAL", "LONG_TERM")).toBe(6.5);
  });

  it("두 축이 함께 누적 적용된다", () => {
    expect(recommendDriftThresholdPct("ISA", "LONG_TERM")).toBe(8.5);
    expect(recommendDriftThresholdPct("ISA", "SHORT_TERM")).toBe(5.5);
  });

  it("null/undefined 입력은 GENERAL/조정없음으로 처리한다", () => {
    expect(recommendDriftThresholdPct(null, null)).toBe(5.0);
    expect(recommendDriftThresholdPct(undefined, undefined)).toBe(5.0);
  });
});
