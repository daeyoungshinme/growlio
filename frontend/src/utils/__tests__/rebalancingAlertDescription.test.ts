import { describe, it, expect } from "vitest";
import { buildAlertDescription } from "@/utils/rebalancingAlertDescription";

describe("buildAlertDescription", () => {
  it("DRIFT_ONLY + NOTIFY: 이탈 임계값과 알림 시각을 포함한다", () => {
    const text = buildAlertDescription(
      "DAILY",
      0,
      1,
      "DRIFT_ONLY",
      5,
      "NOTIFY",
      undefined,
      "08:30",
    );
    expect(text).toBe("비중이 ±5.0% 이상 이탈 시 매일 08:30에 알림을 받습니다.");
  });

  it("DRIFT_ONLY + AUTO: 자동 실행 시각과 문구를 포함한다", () => {
    const text = buildAlertDescription(
      "WEEKLY",
      2,
      1,
      "DRIFT_ONLY",
      3.5,
      "AUTO",
      "09:05",
      undefined,
    );
    expect(text).toBe(
      "비중이 ±3.5% 이상 이탈 시 매주 수요일 09:05에 자동으로 리밸런싱을 실행합니다.",
    );
  });

  it("SCHEDULE_ONLY: 임계값 없이 정기 리포트 문구만 반환한다", () => {
    const text = buildAlertDescription(
      "MONTHLY",
      0,
      15,
      "SCHEDULE_ONLY",
      5,
      "NOTIFY",
      undefined,
      "08:30",
    );
    expect(text).toBe("매월 15일 08:30에 리밸런싱 현황 리포트를 받습니다.");
  });

  it("BOTH: 정기 리포트 + 이탈 즉시 알림 문구를 함께 반환한다", () => {
    const text = buildAlertDescription("QUARTERLY", 0, 10, "BOTH", 7, "AUTO", "10:00", undefined);
    expect(text).toBe(
      "매 3개월 10일 10:00에 정기 리포트를 받으며, 비중이 ±7.0% 이탈 시 즉시 자동으로 리밸런싱을 실행합니다.",
    );
  });

  it("ANNUAL 스케줄 문구를 만든다", () => {
    const text = buildAlertDescription(
      "ANNUAL",
      0,
      1,
      "SCHEDULE_ONLY",
      5,
      "NOTIFY",
      undefined,
      "08:30",
    );
    expect(text).toBe("매년 1일 08:30에 리밸런싱 현황 리포트를 받습니다.");
  });
});
