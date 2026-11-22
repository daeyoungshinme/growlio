import { describe, it, expect } from "vitest";
import { depositReturn, sumDepositReturn } from "@/utils/accountReturn";

describe("depositReturn", () => {
  it("평가액을 순입금(입금 − 출금)과 비교한다", () => {
    const r = depositReturn({
      amountKrw: 12_000_000,
      depositTotal: 11_000_000,
      withdrawalTotal: 1_000_000,
    });
    expect(r).toEqual({ netDeposit: 10_000_000, gain: 2_000_000, pct: 20 });
  });

  it("손실이면 음수", () => {
    const r = depositReturn({ amountKrw: 9_000_000, depositTotal: 10_000_000, withdrawalTotal: 0 });
    expect(r?.gain).toBe(-1_000_000);
    expect(r?.pct).toBe(-10);
  });

  it("순입금이 0 이하면 계산하지 않는다(기록 이전 자금이 있는 계좌의 부풀린 수익 방지)", () => {
    expect(depositReturn({ amountKrw: 5_000_000, depositTotal: 0, withdrawalTotal: 0 })).toBeNull();
    expect(
      depositReturn({ amountKrw: 5_000_000, depositTotal: 1_000_000, withdrawalTotal: 2_000_000 }),
    ).toBeNull();
  });
});

describe("sumDepositReturn", () => {
  it("계산 가능한 계좌만 합친다", () => {
    const r = sumDepositReturn([
      { amountKrw: 12_000_000, depositTotal: 10_000_000, withdrawalTotal: 0 },
      { amountKrw: 5_500_000, depositTotal: 5_000_000, withdrawalTotal: 0 },
      // 입금 기록 없는 계좌 — 평가액을 섞으면 수익이 부풀려진다
      { amountKrw: 30_000_000, depositTotal: 0, withdrawalTotal: 0 },
    ]);
    expect(r).toEqual({
      netDeposit: 15_000_000,
      gain: 2_500_000,
      pct: (2_500_000 / 15_000_000) * 100,
      accountCount: 2,
    });
  });

  it("계산 가능한 계좌가 없으면 null", () => {
    expect(sumDepositReturn([{ amountKrw: 1, depositTotal: 0, withdrawalTotal: 0 }])).toBeNull();
    expect(sumDepositReturn([])).toBeNull();
  });
});
