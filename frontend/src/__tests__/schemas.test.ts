import { describe, it, expect } from "vitest";
import { transactionSchema } from "@/schemas/transaction";
import { tradeSchema } from "@/schemas/trade";

describe("transactionSchema", () => {
  const valid = {
    transaction_type: "DEPOSIT" as const,
    amount: 100000,
    transaction_date: "2024-06-01",
  };

  it("유효한 거래 데이터를 수락한다", () => {
    expect(transactionSchema.safeParse(valid).success).toBe(true);
  });

  it("유효하지 않은 transaction_type은 실패한다", () => {
    const result = transactionSchema.safeParse({ ...valid, transaction_type: "INVALID" });
    expect(result.success).toBe(false);
  });

  it("WITHDRAWAL 타입을 수락한다", () => {
    expect(transactionSchema.safeParse({ ...valid, transaction_type: "WITHDRAWAL" }).success).toBe(
      true,
    );
  });

  it("DIVIDEND 타입을 수락한다", () => {
    expect(transactionSchema.safeParse({ ...valid, transaction_type: "DIVIDEND" }).success).toBe(
      true,
    );
  });

  it("음수 금액은 실패한다", () => {
    const result = transactionSchema.safeParse({ ...valid, amount: -1000 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("금액은 0보다 커야 합니다");
    }
  });

  it("0 금액은 실패한다", () => {
    const result = transactionSchema.safeParse({ ...valid, amount: 0 });
    expect(result.success).toBe(false);
  });

  it("잘못된 날짜 형식은 실패한다", () => {
    const result = transactionSchema.safeParse({ ...valid, transaction_date: "2024/06/01" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("날짜 형식이 올바르지 않습니다");
    }
  });

  it("메모가 500자 이하면 수락한다", () => {
    expect(transactionSchema.safeParse({ ...valid, notes: "a".repeat(500) }).success).toBe(true);
  });

  it("메모가 501자 이상이면 실패한다", () => {
    const result = transactionSchema.safeParse({ ...valid, notes: "a".repeat(501) });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("메모는 500자 이하여야 합니다");
    }
  });

  it("ticker는 선택 사항이다", () => {
    expect(transactionSchema.safeParse({ ...valid, ticker: "005930" }).success).toBe(true);
    expect(transactionSchema.safeParse({ ...valid }).success).toBe(true);
  });
});

describe("tradeSchema", () => {
  const valid = {
    account_id: "acc-1",
    side: "BUY" as const,
    ticker: "005930",
    market: "KOSPI",
    qty: 10,
    price_krw: 70000,
    trade_date: "2026-10-02",
  };

  it("필수값이 모두 있으면 통과", () => {
    expect(tradeSchema.safeParse(valid).success).toBe(true);
  });

  it("종목 미선택(공백 ticker)은 거부", () => {
    const r = tradeSchema.safeParse({ ...valid, ticker: "  " });
    expect(r.success).toBe(false);
    expect(r.error?.issues[0].message).toBe("종목을 선택해주세요");
  });

  it("수량·단가 미입력은 입력 안내 메시지", () => {
    const r = tradeSchema.safeParse({ ...valid, qty: undefined, price_krw: undefined });
    expect(r.success).toBe(false);
    const messages = r.error?.issues.map((i) => i.message);
    expect(messages).toContain("수량을 입력해주세요");
    expect(messages).toContain("단가를 입력해주세요");
  });

  it("0 이하 수량·음수 수수료는 거부", () => {
    expect(tradeSchema.safeParse({ ...valid, qty: 0 }).success).toBe(false);
    expect(tradeSchema.safeParse({ ...valid, fee: -1 }).success).toBe(false);
  });

  it("날짜 형식과 메모 길이를 검사한다", () => {
    expect(tradeSchema.safeParse({ ...valid, trade_date: "2026/10/02" }).success).toBe(false);
    expect(tradeSchema.safeParse({ ...valid, notes: "a".repeat(501) }).success).toBe(false);
  });
});
