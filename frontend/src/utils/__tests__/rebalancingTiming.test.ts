import { describe, expect, it } from "vitest";
import type { PortfolioDriftSummary } from "@/api/rebalancing";
import { driftProgress, getItemsDriftStatus, isDriftingItem } from "../portfolio";
import {
  overseasDeductionRoomNote,
  summaryTiming,
  timingHeadline,
  timingMetaParts,
} from "../rebalancingTiming";

const item = (target: number, diff: number) => ({
  target_weight_pct: target,
  weight_diff_pct: diff,
});

describe("isDriftingItem — 백엔드 drift_rule.is_drifting과 같은 규칙", () => {
  it("절대 기준은 초과일 때만", () => {
    expect(isDriftingItem(item(30, 5), 5)).toBe(false);
    expect(isDriftingItem(item(30, -5.01), 5)).toBe(true);
  });

  it("작은 비중 종목은 상대 기준을 켜야 잡힌다", () => {
    expect(isDriftingItem(item(5, 5), 5)).toBe(false);
    expect(isDriftingItem(item(5, 5), 5, 25)).toBe(true);
    // 경계(목표 10%의 25% = 2.5%p)는 이탈 아님
    expect(isDriftingItem(item(10, 2.5), 5, 25)).toBe(false);
  });

  it("목표 0 항목은 절대 기준만", () => {
    expect(isDriftingItem(item(0, -3), 5, 10)).toBe(false);
  });
});

describe("driftProgress / getItemsDriftStatus", () => {
  it("상대 기준까지 반영해 주의 단계를 정한다", () => {
    const items = [item(10, 2), item(50, 1)];
    expect(driftProgress(items, 5)).toBeCloseTo(0.4);
    expect(driftProgress(items, 5, 25)).toBeCloseTo(0.8);
    expect(getItemsDriftStatus(items, 5)).toBe("stable");
    expect(getItemsDriftStatus(items, 5, 25)).toBe("caution");
    expect(getItemsDriftStatus([item(10, 3)], 5, 25)).toBe("critical");
  });
});

const summary = (over: Partial<PortfolioDriftSummary>): PortfolioDriftSummary => ({
  portfolio_id: "p",
  portfolio_name: "P",
  needs_rebalancing: false,
  threshold_pct: 5,
  max_drift_pct: 1,
  drifted_items_count: 0,
  ...over,
});

describe("summaryTiming", () => {
  it("구버전 응답은 이탈 여부로 대신한다", () => {
    expect(summaryTiming(summary({ needs_rebalancing: true }))).toBe("NOW");
    expect(summaryTiming(summary({}))).toBe("OK");
    expect(summaryTiming(summary({ needs_rebalancing: true, timing: "HOLD" }))).toBe("HOLD");
  });
});

describe("timingMetaParts", () => {
  it("알림이 없으면 '알림 없음', 비용이 없으면 생략", () => {
    expect(timingMetaParts(summary({ has_alert_configured: false }))).toEqual([
      "실행 기록 없음",
      "알림 없음",
    ]);
  });

  it("다음 예정일과 주기, 예상 비용", () => {
    const parts = timingMetaParts(
      summary({
        has_alert_configured: true,
        next_scheduled_date: "2099-12-25",
        schedule_type: "MONTHLY",
        estimated_cost_krw: 120000,
      }),
    );
    expect(parts).toEqual(["실행 기록 없음", "다음 12/25(매월)", "예상 비용 12만원"]);
  });
});

describe("timingHeadline", () => {
  it("행동이 필요한 판정만 센다", () => {
    expect(timingHeadline([summary({ timing: "OK" }), summary({ timing: "WATCH" })])).toBeNull();
    expect(
      timingHeadline([
        summary({ timing: "NOW" }),
        summary({ timing: "NOW" }),
        summary({ timing: "HOLD" }),
      ]),
    ).toBe("지금 2 · 보류 1");
  });
});

describe("overseasDeductionRoomNote", () => {
  it("실현손익을 모르면 안내하지 않는다", () => {
    expect(
      overseasDeductionRoomNote({
        overseas_realized_gain_krw: null,
        overseas_gain_deduction_krw: 2_500_000,
      }),
    ).toBeNull();
  });

  it("남은 공제 여유를 알려 준다", () => {
    expect(
      overseasDeductionRoomNote({
        overseas_realized_gain_krw: 1_000_000,
        overseas_gain_deduction_krw: 2_500_000,
      }),
    ).toContain("150만원");
    expect(
      overseasDeductionRoomNote({
        overseas_realized_gain_krw: 3_000_000,
        overseas_gain_deduction_krw: 2_500_000,
      }),
    ).toContain("이미 다 썼어요");
  });
});
