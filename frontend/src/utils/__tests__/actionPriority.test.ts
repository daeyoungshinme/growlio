import { describe, it, expect, vi, afterEach } from "vitest";
import { ACTION_PRIORITY_STYLE, deadlineLabel } from "@/utils/actionPriority";

describe("deadlineLabel", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("남은 일수를 D-n으로 표시한다", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 11, 26, 15, 0));
    expect(deadlineLabel("2026-12-31")).toBe("12/31까지 (D-5)");
  });

  it("마감 당일은 D-0 (시각과 무관하게 로컬 자정 기준)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 11, 31, 23, 59));
    expect(deadlineLabel("2026-12-31")).toBe("12/31까지 (D-0)");
  });

  it("지났으면 마감으로 표시한다", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2027, 0, 1, 0, 1));
    expect(deadlineLabel("2026-12-31")).toBe("12/31 마감");
  });
});

describe("ACTION_PRIORITY_STYLE", () => {
  it("세 우선순위 모두 라벨이 있다", () => {
    expect(ACTION_PRIORITY_STYLE.HIGH.label).toBe("우선");
    expect(ACTION_PRIORITY_STYLE.MEDIUM.label).toBe("권장");
    expect(ACTION_PRIORITY_STYLE.LOW.label).toBe("참고");
  });
});
