import { describe, it, expect } from "vitest";
import { loginSchema, registerSchema, resetPasswordSchema } from "@/schemas/auth";
import { transactionSchema } from "@/schemas/transaction";
import { investGoalSchema } from "@/schemas/settings";
import { portfolioItemSchema, portfolioCreateSchema } from "@/schemas/portfolios";
import { realEstateDetailsSchema, assetAccountCreateSchema, manualPositionSchema } from "@/schemas/assets";

// ────────────────────────────────────────────
// auth schemas
// ────────────────────────────────────────────
describe("loginSchema", () => {
  it("유효한 이메일/비밀번호를 수락한다", () => {
    const result = loginSchema.safeParse({ email: "user@example.com", password: "pass123" });
    expect(result.success).toBe(true);
  });

  it("이메일 형식이 잘못되면 실패한다", () => {
    const result = loginSchema.safeParse({ email: "not-an-email", password: "pass123" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("올바른 이메일 형식이 아닙니다");
    }
  });

  it("빈 이메일이면 실패한다", () => {
    const result = loginSchema.safeParse({ email: "", password: "pass123" });
    expect(result.success).toBe(false);
  });

  it("비밀번호가 빈 문자열이면 실패한다", () => {
    const result = loginSchema.safeParse({ email: "user@example.com", password: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("비밀번호를 입력해주세요");
    }
  });

  it("두 필드가 모두 비면 두 오류를 반환한다", () => {
    const result = loginSchema.safeParse({ email: "", password: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.length).toBeGreaterThanOrEqual(2);
    }
  });
});

describe("registerSchema", () => {
  const valid = { email: "user@example.com", password: "password123", confirmPassword: "password123" };

  it("유효한 회원가입 데이터를 수락한다", () => {
    expect(registerSchema.safeParse(valid).success).toBe(true);
  });

  it("비밀번호가 8자 미만이면 실패한다", () => {
    const result = registerSchema.safeParse({ ...valid, password: "short", confirmPassword: "short" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("비밀번호는 8자 이상이어야 합니다");
    }
  });

  it("비밀번호 불일치 시 실패한다", () => {
    const result = registerSchema.safeParse({ ...valid, confirmPassword: "different123" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const mismatch = result.error.issues.find((i) => i.path.includes("confirmPassword"));
      expect(mismatch?.message).toBe("비밀번호가 일치하지 않습니다");
    }
  });

  it("이메일 형식 오류 시 실패한다", () => {
    const result = registerSchema.safeParse({ ...valid, email: "bad-email" });
    expect(result.success).toBe(false);
  });

  it("정확히 8자 비밀번호는 유효하다", () => {
    expect(registerSchema.safeParse({ ...valid, password: "12345678", confirmPassword: "12345678" }).success).toBe(true);
  });
});

describe("resetPasswordSchema", () => {
  it("유효한 데이터를 수락한다", () => {
    expect(resetPasswordSchema.safeParse({ password: "newpass12", confirmPassword: "newpass12" }).success).toBe(true);
  });

  it("8자 미만 비밀번호는 실패한다", () => {
    const result = resetPasswordSchema.safeParse({ password: "short", confirmPassword: "short" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("비밀번호는 8자 이상이어야 합니다");
    }
  });

  it("비밀번호 불일치 시 실패한다", () => {
    const result = resetPasswordSchema.safeParse({ password: "newpass12", confirmPassword: "different" });
    expect(result.success).toBe(false);
    if (!result.success) {
      const mismatch = result.error.issues.find((i) => i.path.includes("confirmPassword"));
      expect(mismatch?.message).toBe("비밀번호가 일치하지 않습니다");
    }
  });
});

// ────────────────────────────────────────────
// transaction schema
// ────────────────────────────────────────────
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
    expect(transactionSchema.safeParse({ ...valid, transaction_type: "WITHDRAWAL" }).success).toBe(true);
  });

  it("DIVIDEND 타입을 수락한다", () => {
    expect(transactionSchema.safeParse({ ...valid, transaction_type: "DIVIDEND" }).success).toBe(true);
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

// ────────────────────────────────────────────
// settings / investGoal schema
// ────────────────────────────────────────────
describe("investGoalSchema", () => {
  it("모든 필드가 선택 사항이므로 빈 객체도 유효하다", () => {
    expect(investGoalSchema.safeParse({}).success).toBe(true);
  });

  it("유효한 전체 데이터를 수락한다", () => {
    expect(
      investGoalSchema.safeParse({
        annual_investment_goal: 12000000,
        target_asset_amount: 500000000,
        target_year: 2035,
      }).success
    ).toBe(true);
  });

  it("annual_investment_goal이 음수이면 실패한다", () => {
    const result = investGoalSchema.safeParse({ annual_investment_goal: -1 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("목표 금액은 0 이상이어야 합니다");
    }
  });

  it("annual_investment_goal이 0이면 허용된다", () => {
    expect(investGoalSchema.safeParse({ annual_investment_goal: 0 }).success).toBe(true);
  });

  it("target_year가 2020 미만이면 실패한다", () => {
    const result = investGoalSchema.safeParse({ target_year: 2019 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("2020년 이후 연도를 입력해주세요");
    }
  });

  it("target_year가 2101 이상이면 실패한다", () => {
    const result = investGoalSchema.safeParse({ target_year: 2101 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("2100년 이전 연도를 입력해주세요");
    }
  });

  it("target_year가 2020이면 허용된다", () => {
    expect(investGoalSchema.safeParse({ target_year: 2020 }).success).toBe(true);
  });

  it("target_year가 2100이면 허용된다", () => {
    expect(investGoalSchema.safeParse({ target_year: 2100 }).success).toBe(true);
  });

  it("소수점 target_year는 실패한다", () => {
    const result = investGoalSchema.safeParse({ target_year: 2030.5 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("정수 연도를 입력해주세요");
    }
  });

  it("target_asset_amount가 음수이면 실패한다", () => {
    const result = investGoalSchema.safeParse({ target_asset_amount: -1000 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("목표 자산은 0 이상이어야 합니다");
    }
  });
});

// ────────────────────────────────────────────
// portfolio schemas
// ────────────────────────────────────────────
describe("portfolioItemSchema", () => {
  const valid = { ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 50 };

  it("유효한 종목을 수락한다", () => {
    expect(portfolioItemSchema.safeParse(valid).success).toBe(true);
  });

  it("티커가 빈 문자열이면 실패한다", () => {
    const result = portfolioItemSchema.safeParse({ ...valid, ticker: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("티커를 입력해주세요");
    }
  });

  it("시장이 빈 문자열이면 실패한다", () => {
    const result = portfolioItemSchema.safeParse({ ...valid, market: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("시장을 선택해주세요");
    }
  });

  it("비중이 0 미만이면 실패한다", () => {
    const result = portfolioItemSchema.safeParse({ ...valid, weight: -1 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("비중은 0 이상이어야 합니다");
    }
  });

  it("비중이 100 초과이면 실패한다", () => {
    const result = portfolioItemSchema.safeParse({ ...valid, weight: 101 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("비중은 100 이하여야 합니다");
    }
  });

  it("비중이 경계값 0과 100은 허용된다", () => {
    expect(portfolioItemSchema.safeParse({ ...valid, weight: 0 }).success).toBe(true);
    expect(portfolioItemSchema.safeParse({ ...valid, weight: 100 }).success).toBe(true);
  });
});

describe("portfolioCreateSchema", () => {
  const validItem = { ticker: "005930", name: "삼성전자", market: "KOSPI", weight: 100 };
  const valid = { name: "내 포트폴리오", items: [validItem] };

  it("유효한 포트폴리오를 수락한다", () => {
    expect(portfolioCreateSchema.safeParse(valid).success).toBe(true);
  });

  it("이름이 빈 문자열이면 실패한다", () => {
    const result = portfolioCreateSchema.safeParse({ ...valid, name: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("포트폴리오 이름을 입력해주세요");
    }
  });

  it("이름이 100자 초과이면 실패한다", () => {
    const result = portfolioCreateSchema.safeParse({ ...valid, name: "a".repeat(101) });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("이름은 100자 이하여야 합니다");
    }
  });

  it("items가 빈 배열이면 실패한다", () => {
    const result = portfolioCreateSchema.safeParse({ ...valid, items: [] });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("종목을 하나 이상 추가해주세요");
    }
  });

  it("items가 51개 이상이면 실패한다", () => {
    const manyItems = Array.from({ length: 51 }, (_, i) => ({
      ...validItem,
      ticker: `TICK${i}`,
      weight: 100 / 51,
    }));
    const result = portfolioCreateSchema.safeParse({ ...valid, items: manyItems });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("종목은 최대 50개까지 추가할 수 있습니다");
    }
  });

  it("비중 합이 100이 아니면 실패한다", () => {
    const items = [
      { ...validItem, weight: 60 },
      { ...validItem, ticker: "035720", name: "카카오", weight: 30 },
    ];
    const result = portfolioCreateSchema.safeParse({ ...valid, items });
    expect(result.success).toBe(false);
    if (!result.success) {
      const refineErr = result.error.issues.find((i) => i.path.includes("items"));
      expect(refineErr?.message).toBe("종목 비중 합계가 100%여야 합니다");
    }
  });

  it("비중 합이 정확히 100이면 수락한다", () => {
    const items = [
      { ...validItem, weight: 60 },
      { ...validItem, ticker: "035720", name: "카카오", weight: 40 },
    ];
    expect(portfolioCreateSchema.safeParse({ ...valid, items }).success).toBe(true);
  });

  it("base_type이 STOCK_ONLY면 수락한다", () => {
    expect(portfolioCreateSchema.safeParse({ ...valid, base_type: "STOCK_ONLY" }).success).toBe(true);
  });

  it("base_type이 TOTAL_ASSETS면 수락한다", () => {
    expect(portfolioCreateSchema.safeParse({ ...valid, base_type: "TOTAL_ASSETS" }).success).toBe(true);
  });

  it("base_type이 유효하지 않으면 실패한다", () => {
    const result = portfolioCreateSchema.safeParse({ ...valid, base_type: "INVALID" });
    expect(result.success).toBe(false);
  });

  it("account_ids에 유효한 UUID 배열을 수락한다", () => {
    expect(
      portfolioCreateSchema.safeParse({
        ...valid,
        account_ids: ["550e8400-e29b-41d4-a716-446655440000"],
      }).success
    ).toBe(true);
  });

  it("account_ids에 유효하지 않은 UUID가 있으면 실패한다", () => {
    const result = portfolioCreateSchema.safeParse({ ...valid, account_ids: ["not-a-uuid"] });
    expect(result.success).toBe(false);
  });

  it("account_ids가 null이면 수락한다", () => {
    expect(portfolioCreateSchema.safeParse({ ...valid, account_ids: null }).success).toBe(true);
  });
});

// ────────────────────────────────────────────
// asset schemas
// ────────────────────────────────────────────
describe("realEstateDetailsSchema", () => {
  const valid = { address: "서울시 강남구", property_type: "아파트" };

  it("유효한 부동산 상세정보를 수락한다", () => {
    expect(realEstateDetailsSchema.safeParse(valid).success).toBe(true);
  });

  it("주소가 빈 문자열이면 실패한다", () => {
    const result = realEstateDetailsSchema.safeParse({ ...valid, address: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("주소를 입력해주세요");
    }
  });

  it("부동산 유형이 빈 문자열이면 실패한다", () => {
    const result = realEstateDetailsSchema.safeParse({ ...valid, property_type: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("부동산 유형을 선택해주세요");
    }
  });

  it("매입가가 0 이하이면 실패한다", () => {
    const result = realEstateDetailsSchema.safeParse({ ...valid, purchase_price_krw: 0 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("매입가는 0보다 커야 합니다");
    }
  });

  it("모기지 잔액이 0이면 허용된다", () => {
    expect(realEstateDetailsSchema.safeParse({ ...valid, mortgage_balance_krw: 0 }).success).toBe(true);
  });

  it("모기지 잔액이 음수이면 실패한다", () => {
    const result = realEstateDetailsSchema.safeParse({ ...valid, mortgage_balance_krw: -1000 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("모기지 잔액은 0 이상이어야 합니다");
    }
  });

  it("선택 필드는 없어도 된다", () => {
    expect(realEstateDetailsSchema.safeParse(valid).success).toBe(true);
  });
});

describe("assetAccountCreateSchema", () => {
  const valid = { name: "한국투자증권 계좌", asset_type: "STOCK_KIS" };

  it("최소 필수 필드로 수락한다", () => {
    expect(assetAccountCreateSchema.safeParse(valid).success).toBe(true);
  });

  it("계좌명이 빈 문자열이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, name: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("계좌명을 입력해주세요");
    }
  });

  it("계좌명이 100자 초과이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, name: "a".repeat(101) });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("계좌명은 100자 이하여야 합니다");
    }
  });

  it("자산 유형이 빈 문자열이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, asset_type: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("자산 유형을 선택해주세요");
    }
  });

  it("유효한 KIS 계좌번호 형식 (12345678-01)을 수락한다", () => {
    expect(assetAccountCreateSchema.safeParse({ ...valid, kis_account_no: "12345678-01" }).success).toBe(true);
  });

  it("유효한 KIS 계좌번호 형식 (1234567890)을 수락한다", () => {
    expect(assetAccountCreateSchema.safeParse({ ...valid, kis_account_no: "1234567890" }).success).toBe(true);
  });

  it("잘못된 KIS 계좌번호 형식이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, kis_account_no: "INVALID" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("KIS 계좌번호 형식이 올바르지 않습니다 (예: 12345678-01)");
    }
  });

  it("KIS 계좌번호가 빈 문자열이면 수락한다 (or z.literal(''))", () => {
    expect(assetAccountCreateSchema.safeParse({ ...valid, kis_account_no: "" }).success).toBe(true);
  });

  it("manual_amount가 0 이하이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, manual_amount: 0 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("금액은 0보다 커야 합니다");
    }
  });

  it("deposit_krw가 음수이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, deposit_krw: -100 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("예수금은 0 이상이어야 합니다");
    }
  });

  it("deposit_usd가 음수이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, deposit_usd: -10 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("USD 예수금은 0 이상이어야 합니다");
    }
  });

  it("notes가 500자 이하이면 수락한다", () => {
    expect(assetAccountCreateSchema.safeParse({ ...valid, notes: "a".repeat(500) }).success).toBe(true);
  });

  it("notes가 501자 이상이면 실패한다", () => {
    const result = assetAccountCreateSchema.safeParse({ ...valid, notes: "a".repeat(501) });
    expect(result.success).toBe(false);
  });
});

describe("manualPositionSchema", () => {
  const valid = {
    ticker: "005930",
    name: "삼성전자",
    market: "KOSPI" as const,
    qty: 10,
    avg_price: 70000,
  };

  it("유효한 포지션 데이터를 수락한다", () => {
    expect(manualPositionSchema.safeParse(valid).success).toBe(true);
  });

  it("티커가 빈 문자열이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, ticker: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("티커를 입력해주세요");
    }
  });

  it("티커가 21자 이상이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, ticker: "a".repeat(21) });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("티커는 20자 이하여야 합니다");
    }
  });

  it("종목명이 빈 문자열이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, name: "" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("종목명을 입력해주세요");
    }
  });

  it("유효하지 않은 market이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, market: "INVALID" });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("유효하지 않은 시장입니다");
    }
  });

  it("모든 유효한 시장을 수락한다", () => {
    const markets = ["KOSPI", "KOSDAQ", "KONEX", "NYSE", "NASDAQ", "AMEX", "TSE", "HKEX", "LSE"] as const;
    for (const market of markets) {
      expect(manualPositionSchema.safeParse({ ...valid, market }).success).toBe(true);
    }
  });

  it("수량이 0 이하이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, qty: 0 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("수량은 0보다 커야 합니다");
    }
  });

  it("수량이 1,000,000 초과이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, qty: 1_000_001 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("수량은 100만 이하여야 합니다");
    }
  });

  it("평균단가가 0 이하이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, avg_price: 0 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("평균단가는 0보다 커야 합니다");
    }
  });

  it("달러 평균단가가 0 이하이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, avg_price_usd: 0 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("달러 평균단가는 0보다 커야 합니다");
    }
  });

  it("달러 평균단가는 선택 사항이다", () => {
    expect(manualPositionSchema.safeParse({ ...valid }).success).toBe(true);
    expect(manualPositionSchema.safeParse({ ...valid, avg_price_usd: null }).success).toBe(true);
    expect(manualPositionSchema.safeParse({ ...valid, avg_price_usd: 50.5 }).success).toBe(true);
  });

  it("환율이 9999 초과이면 실패한다", () => {
    const result = manualPositionSchema.safeParse({ ...valid, usd_rate: 10000 });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toBe("환율은 10,000 미만이어야 합니다");
    }
  });

  it("환율이 null이면 수락한다", () => {
    expect(manualPositionSchema.safeParse({ ...valid, usd_rate: null }).success).toBe(true);
  });
});
