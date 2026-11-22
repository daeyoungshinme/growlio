import { describe, it, expect } from "vitest";
import { bankBalanceKrw, parseAccountSortMode, sortAccounts } from "@/utils/accountSort";

type Row = { name: string; amount: number };
const rows: Row[] = [
  { name: "하나", amount: 100 },
  { name: "가나", amount: 300 },
  { name: "다라", amount: 300 },
];
const amountOf = (r: Row) => r.amount;
const nameOf = (r: Row) => r.name;

describe("sortAccounts", () => {
  it("default는 서버 순서 그대로(새 배열)", () => {
    const out = sortAccounts(rows, "default", amountOf, nameOf);
    expect(out).toEqual(rows);
    expect(out).not.toBe(rows);
  });

  it("금액순은 큰 금액부터, 같으면 원래 순서", () => {
    expect(sortAccounts(rows, "amount", amountOf, nameOf).map((r) => r.name)).toEqual([
      "가나",
      "다라",
      "하나",
    ]);
  });

  it("이름순은 한국어 가나다순", () => {
    expect(sortAccounts(rows, "name", amountOf, nameOf).map((r) => r.name)).toEqual([
      "가나",
      "다라",
      "하나",
    ]);
  });
});

describe("parseAccountSortMode", () => {
  it("모르는 값·저장값 없음은 default", () => {
    expect(parseAccountSortMode(null)).toBe("default");
    expect(parseAccountSortMode("weird")).toBe("default");
    expect(parseAccountSortMode("amount")).toBe("amount");
  });
});

describe("bankBalanceKrw", () => {
  it("예수금 필드가 없으면 수기 금액", () => {
    expect(
      bankBalanceKrw({ deposit_krw: null, deposit_usd: null, manual_amount: 5000 }, 1300).krw,
    ).toBe(5000);
  });

  it("원화 + 달러 환산", () => {
    const b = bankBalanceKrw({ deposit_krw: 1000, deposit_usd: 10, manual_amount: null }, 1300);
    expect(b.krw).toBe(14000);
    expect(b.usdPending).toBe(false);
  });

  it("환율이 없으면 달러를 더하지 않고 대기 표시", () => {
    const b = bankBalanceKrw({ deposit_krw: 1000, deposit_usd: 10, manual_amount: null }, null);
    expect(b.krw).toBe(1000);
    expect(b.usdPending).toBe(true);
  });
});
