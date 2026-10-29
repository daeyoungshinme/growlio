import { describe, expect, it } from "vitest";
import { resolvePushDeepLink } from "@/hooks/usePushNotifications";

/** 링크는 퍼센트 인코딩돼 있어 읽기 쉬운 형태로 비교한다 */
const link = (data: Parameters<typeof resolvePushDeepLink>[0]) => {
  const url = resolvePushDeepLink(data);
  return url && decodeURIComponent(url);
};

describe("resolvePushDeepLink", () => {
  it("returns null when data is missing", () => {
    expect(resolvePushDeepLink(undefined)).toBeNull();
    expect(resolvePushDeepLink(null)).toBeNull();
    expect(resolvePushDeepLink({})).toBeNull();
  });

  it("returns null for unknown type", () => {
    expect(resolvePushDeepLink({ type: "UNKNOWN" })).toBeNull();
  });

  it("routes REBALANCING with portfolio_id to the execution tab", () => {
    expect(link({ type: "REBALANCING", portfolio_id: "abc-123" })).toBe(
      "/rebalancing?rtab=포트폴리오&portfolioId=abc-123&openExecution=1",
    );
  });

  it("falls back to the diagnosis tab when REBALANCING has no portfolio_id", () => {
    expect(link({ type: "REBALANCING" })).toBe("/rebalancing?rtab=진단");
  });

  it("routes plan pending/executed pushes to the history tab", () => {
    expect(link({ type: "REBALANCING_PLAN_PENDING", portfolio_id: "x" })).toBe(
      "/rebalancing?rtab=이력",
    );
    expect(link({ type: "REBALANCING_EXECUTED", portfolio_id: "x" })).toBe(
      "/rebalancing?rtab=이력",
    );
  });

  it("routes DCA_CASH_SHORTFALL to the savings plan tab", () => {
    expect(resolvePushDeepLink({ type: "DCA_CASH_SHORTFALL" })).toBe(
      `/invest-plan?tab=${encodeURIComponent("적립 계획")}`,
    );
  });

  it("routes RECOMMENDATION_DRIFT to the recommendation tab", () => {
    expect(link({ type: "RECOMMENDATION_DRIFT" })).toBe("/rebalancing?rtab=목표 조정&gmode=추천");
  });

  it("routes tactical regime pushes to the goal-adjust tab in tactical mode (plans/64)", () => {
    expect(link({ type: "tactical_regime" })).toBe("/rebalancing?rtab=목표 조정&gmode=전술");
  });

  it("routes MARKET_SIGNAL to the diagnosis tab", () => {
    expect(link({ type: "MARKET_SIGNAL" })).toBe("/rebalancing?rtab=진단");
  });

  it("자동 실행 보류 알림은 해당 포트폴리오 자동화 설정으로, 실행 실패는 이력으로 연다 (plans/63 P3-4)", () => {
    for (const type of [
      "REBALANCING_TAX_GATE_BLOCKED",
      "REBALANCING_MARKET_GATE_BLOCKED",
      "REBALANCING_DAILY_CAP_BLOCKED",
    ]) {
      expect(link({ type, portfolio_id: "p1" })).toBe(
        "/rebalancing?rtab=포트폴리오&portfolioId=p1&openAlert=1",
      );
    }
    expect(link({ type: "REBALANCING_PLAN_EXECUTION_FAILED" })).toBe("/rebalancing?rtab=이력");
  });

  it("챌린지·시장 요약·연말 절세 알림도 해당 화면으로 연다 (plans/90 B5)", () => {
    expect(link({ type: "CHALLENGE_REMINDER" })).toBe("/invest-plan?tab=챌린지");
    expect(link({ type: "CHALLENGE_WRAPUP" })).toBe("/invest-plan?tab=챌린지");
    expect(link({ type: "YEAR_END_TAX_REMINDER" })).toBe("/invest-plan?tab=절세");
    expect(link({ type: "MARKET_SIGNAL_DIGEST" })).toBe("/rebalancing?rtab=진단");
  });
});
