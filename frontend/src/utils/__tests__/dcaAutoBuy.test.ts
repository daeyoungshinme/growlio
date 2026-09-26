import { describe, it, expect } from "vitest";
import {
  isDcaAutoBuyPreset,
  describeDcaAutoBuy,
  dcaAccountCashKrw,
  dcaCashShortfallKrw,
} from "@/utils/dcaAutoBuy";
import type { RebalancingAlert } from "@/api/alerts";

const baseAlert: RebalancingAlert = {
  id: "alert-1",
  portfolio_id: "port-1",
  threshold_pct: 0.5,
  schedule_type: "MONTHLY",
  schedule_day_of_week: null,
  schedule_day_of_month: 25,
  trigger_condition: "SCHEDULE_ONLY",
  mode: "AUTO",
  strategy: "BUY_ONLY",
  account_id: "acc-1",
  order_type: "MARKET",
  market_condition_mode: "DISABLED",
  auto_execution_time: "09:05",
  notify_time: "08:30",
  buy_wait_minutes: 10,
  tax_impact_gate_mode: "DISABLED",
  max_tax_impact_krw: null,
  is_active: true,
  last_triggered_at: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("isDcaAutoBuyPreset", () => {
  it("MONTHLY + SCHEDULE_ONLY + AUTO + BUY_ONLY 조합이면 true", () => {
    expect(isDcaAutoBuyPreset(baseAlert)).toBe(true);
  });

  it("threshold_pct 값이 달라도 나머지 4개 필드만 맞으면 true다 (사용자가 임계값을 직접 조정했을 수 있음)", () => {
    expect(isDcaAutoBuyPreset({ ...baseAlert, threshold_pct: 3 })).toBe(true);
  });

  it("null/undefined는 false", () => {
    expect(isDcaAutoBuyPreset(null)).toBe(false);
    expect(isDcaAutoBuyPreset(undefined)).toBe(false);
  });

  it("schedule_type이 MONTHLY가 아니면 false", () => {
    expect(isDcaAutoBuyPreset({ ...baseAlert, schedule_type: "WEEKLY" })).toBe(false);
  });

  it("trigger_condition이 SCHEDULE_ONLY가 아니면 false", () => {
    expect(isDcaAutoBuyPreset({ ...baseAlert, trigger_condition: "DRIFT_ONLY" })).toBe(false);
  });

  it("mode가 AUTO가 아니면 false", () => {
    expect(isDcaAutoBuyPreset({ ...baseAlert, mode: "NOTIFY" })).toBe(false);
  });

  it("strategy가 BUY_ONLY가 아니면 false", () => {
    expect(isDcaAutoBuyPreset({ ...baseAlert, strategy: "FULL" })).toBe(false);
  });
});

describe("describeDcaAutoBuy", () => {
  it("프리셋과 일치하면 매월 며칠인지 요약 문장을 반환한다", () => {
    expect(describeDcaAutoBuy(baseAlert)).toBe("매월 25일 자동매수 중");
  });

  it("schedule_day_of_month가 없으면 1일로 폴백한다", () => {
    expect(describeDcaAutoBuy({ ...baseAlert, schedule_day_of_month: null })).toBe(
      "매월 1일 자동매수 중",
    );
  });

  it("프리셋이 아니면 빈 문자열을 반환한다", () => {
    expect(describeDcaAutoBuy({ ...baseAlert, mode: "NOTIFY" })).toBe("");
  });

  it("alert가 없으면 빈 문자열을 반환한다", () => {
    expect(describeDcaAutoBuy(null)).toBe("");
  });
});

describe("dcaAccountCashKrw / dcaCashShortfallKrw (E5)", () => {
  it("해외 종목이 있을 때만 달러 예수금을 환산해 더한다", () => {
    const account = { deposit_krw: 100_000, deposit_usd: 100 };
    expect(dcaAccountCashKrw(account, ["KOSPI"], 1400)).toBe(100_000);
    expect(dcaAccountCashKrw(account, ["KOSPI", "NASDAQ"], 1400)).toBe(240_000);
    expect(dcaAccountCashKrw(account, ["NASDAQ"], null)).toBe(100_000);
  });

  it("월 적립액보다 적을 때만 부족분을 반환한다", () => {
    expect(dcaCashShortfallKrw(300_000, 1_000_000)).toBe(700_000);
    expect(dcaCashShortfallKrw(1_000_000, 1_000_000)).toBeNull();
    expect(dcaCashShortfallKrw(0, null)).toBeNull();
  });
});
