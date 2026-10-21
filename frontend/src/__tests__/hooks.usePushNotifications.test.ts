import { describe, expect, it } from "vitest";
import { resolvePushDeepLink } from "@/hooks/usePushNotifications";

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
    expect(resolvePushDeepLink({ type: "REBALANCING", portfolio_id: "abc-123" })).toBe(
      "/rebalancing?rtab=포트폴리오&portfolioId=abc-123&openExecution=1",
    );
  });

  it("falls back to the diagnosis tab when REBALANCING has no portfolio_id", () => {
    expect(resolvePushDeepLink({ type: "REBALANCING" })).toBe("/rebalancing?rtab=진단");
  });

  it("routes plan pending/executed pushes to the history tab", () => {
    expect(resolvePushDeepLink({ type: "REBALANCING_PLAN_PENDING", portfolio_id: "x" })).toBe(
      "/rebalancing?rtab=이력",
    );
    expect(resolvePushDeepLink({ type: "REBALANCING_EXECUTED", portfolio_id: "x" })).toBe(
      "/rebalancing?rtab=이력",
    );
  });

  it("routes DCA_CASH_SHORTFALL to the savings plan tab", () => {
    expect(resolvePushDeepLink({ type: "DCA_CASH_SHORTFALL" })).toBe(
      `/invest-plan?tab=${encodeURIComponent("적립 계획")}`,
    );
  });

  it("routes RECOMMENDATION_DRIFT to the recommendation tab", () => {
    expect(resolvePushDeepLink({ type: "RECOMMENDATION_DRIFT" })).toBe("/rebalancing?rtab=추천");
  });

  it("routes MARKET_SIGNAL to the diagnosis tab", () => {
    expect(resolvePushDeepLink({ type: "MARKET_SIGNAL" })).toBe("/rebalancing?rtab=진단");
  });

  it("자동 실행 보류 알림은 해당 포트폴리오 자동화 설정으로, 실행 실패는 이력으로 연다 (plans/63 P3-4)", () => {
    for (const type of [
      "REBALANCING_TAX_GATE_BLOCKED",
      "REBALANCING_MARKET_GATE_BLOCKED",
      "REBALANCING_DAILY_CAP_BLOCKED",
    ]) {
      expect(resolvePushDeepLink({ type, portfolio_id: "p1" })).toBe(
        "/rebalancing?rtab=포트폴리오&portfolioId=p1&openAlert=1",
      );
    }
    expect(resolvePushDeepLink({ type: "REBALANCING_PLAN_EXECUTION_FAILED" })).toBe(
      "/rebalancing?rtab=이력",
    );
  });
});
