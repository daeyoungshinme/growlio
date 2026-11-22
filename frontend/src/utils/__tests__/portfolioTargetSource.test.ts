import { describe, expect, it } from "vitest";
import { targetSourceLabel } from "@/utils/portfolioTargetSource";

describe("targetSourceLabel (plans/145)", () => {
  it("기록 이전이면 표시하지 않는다", () => {
    expect(targetSourceLabel({ target_source: null, target_source_at: null })).toBeNull();
    expect(targetSourceLabel({})).toBeNull();
  });

  it("출처와 로컬 날짜", () => {
    const at = new Date(2026, 10, 20, 8, 0).toISOString();
    expect(targetSourceLabel({ target_source: "RECOMMENDATION", target_source_at: at })).toBe(
      "목표: 추천 적용 · 11.20",
    );
  });

  it("시각이 없으면 출처만", () => {
    expect(targetSourceLabel({ target_source: "TACTICAL", target_source_at: null })).toBe(
      "목표: 전술 적용",
    );
  });
});
