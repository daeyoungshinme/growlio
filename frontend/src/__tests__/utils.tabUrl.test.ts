import { describe, expect, it } from "vitest";

import { MARKET_ALERT_SECTION } from "@/constants/tabs";
import {
  assetManagementUrl,
  investPlanUrl,
  notificationSettingsUrl,
  portfolioUrl,
} from "@/utils/tabUrl";

// 이메일·푸시·백엔드 링크와 같은 문자열을 유지하는지 고정한다(plans/107 C1)
describe("tabUrl", () => {
  it("builds asset links", () => {
    expect(portfolioUrl()).toBe("/assets?tab=투자현황");
    expect(portfolioUrl("배당")).toBe("/assets?tab=투자현황&portfolioTab=배당");
    expect(assetManagementUrl()).toBe("/assets?tab=계좌관리");
    expect(assetManagementUrl("증권계좌")).toBe("/assets?tab=계좌관리&atab=증권계좌");
    expect(assetManagementUrl("내역", "매수 내역")).toBe(
      "/assets?tab=계좌관리&atab=내역&history=매수 내역",
    );
  });

  it("builds invest plan links", () => {
    expect(investPlanUrl("챌린지")).toBe("/invest-plan?tab=챌린지");
    expect(investPlanUrl("적립 계획", { from: "recommendation" })).toBe(
      "/invest-plan?tab=적립 계획&from=recommendation",
    );
    expect(investPlanUrl("절세", { taxTab: "한도 현황" })).toBe(
      "/invest-plan?tab=절세&taxTab=한도 현황",
    );
  });

  it("builds notification settings links", () => {
    expect(notificationSettingsUrl()).toBe("/settings/notifications");
    expect(notificationSettingsUrl("발송 이력")).toBe("/settings/notifications?atab=발송 이력");
    expect(notificationSettingsUrl(MARKET_ALERT_SECTION)).toBe(
      "/settings/notifications?atab=시장 신호 알림",
    );
  });
});
