import { describe, expect, it } from "vitest";
import { depositDeltaAfterEdit } from "@/utils/depositDelta";

describe("depositDeltaAfterEdit", () => {
  const deposit = { amount: 500_000, transaction_type: "DEPOSIT" };

  it("금액이 그대로면(메모만 수정) 제안할 금액이 없다", () => {
    expect(depositDeltaAfterEdit(deposit, 500_000, "DEPOSIT").amount).toBe(0);
  });

  it("입금액을 늘리면 늘어난 만큼만 입금으로 제안한다", () => {
    expect(depositDeltaAfterEdit(deposit, 700_000, "DEPOSIT")).toEqual({
      amount: 200_000,
      txType: "DEPOSIT",
    });
  });

  it("입금액을 줄이면 줄어든 만큼 출금으로 제안한다", () => {
    expect(depositDeltaAfterEdit(deposit, 300_000, "DEPOSIT")).toEqual({
      amount: 200_000,
      txType: "WITHDRAWAL",
    });
  });

  it("입금을 출금으로 바꾸면 양쪽을 합친 금액을 제안한다", () => {
    expect(depositDeltaAfterEdit(deposit, 500_000, "WITHDRAWAL")).toEqual({
      amount: 1_000_000,
      txType: "WITHDRAWAL",
    });
  });

  it("출금액을 줄이면 예수금이 늘어나는 쪽으로 제안한다", () => {
    const withdrawal = { amount: 500_000, transaction_type: "WITHDRAWAL" };
    expect(depositDeltaAfterEdit(withdrawal, 300_000, "WITHDRAWAL")).toEqual({
      amount: 200_000,
      txType: "DEPOSIT",
    });
  });

  it("이전 값이 없으면 전액을 제안한다", () => {
    expect(depositDeltaAfterEdit(null, 100, "DEPOSIT")).toEqual({ amount: 100, txType: "DEPOSIT" });
  });
});
