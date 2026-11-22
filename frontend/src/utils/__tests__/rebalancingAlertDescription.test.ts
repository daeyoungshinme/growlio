import { describe, it, expect } from "vitest";
import { buildAlertDescription, describeTradeOptions } from "@/utils/rebalancingAlertDescription";

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

  it("SCHEDULE_ONLY + AUTO: 리포트가 아닌 자동 실행 문구를 반환한다 (정기 적립식 자동매수)", () => {
    const text = buildAlertDescription(
      "MONTHLY",
      0,
      25,
      "SCHEDULE_ONLY",
      0.5,
      "AUTO",
      "09:05",
      undefined,
    );
    expect(text).toBe("매월 25일 09:05에 자동으로 리밸런싱을 실행합니다.");
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

describe("describeTradeOptions (plans/145)", () => {
  const base = {
    mode: "AUTO" as const,
    triggerCondition: "DRIFT_ONLY" as const,
    tradeToBand: false,
    minTradeKrw: null,
    isDcaAmount: false,
    dcaAllocationMode: "TARGET" as const,
  };

  it("기본값이면 문구 없음", () => {
    expect(describeTradeOptions(base)).toBeNull();
  });

  it("경계 거래·최소 거래액을 한 줄로", () => {
    expect(describeTradeOptions({ ...base, tradeToBand: true, minTradeKrw: 100_000 })).toBe(
      "이탈 종목은 허용 범위 경계까지만 거래합니다 · 100,000원 미만 주문은 건너뜁니다.",
    );
  });

  it("정액 적립 부족분 우선", () => {
    expect(
      describeTradeOptions({ ...base, isDcaAmount: true, dcaAllocationMode: "GAP_FIRST" }),
    ).toBe("적립 금액은 목표보다 모자란 종목부터 채웁니다.");
  });

  it("NOTIFY·스케줄만이면 경계 거래 문구를 넣지 않는다", () => {
    expect(describeTradeOptions({ ...base, mode: "NOTIFY", tradeToBand: true })).toBeNull();
    expect(
      describeTradeOptions({ ...base, triggerCondition: "SCHEDULE_ONLY", tradeToBand: true }),
    ).toBeNull();
  });
});
