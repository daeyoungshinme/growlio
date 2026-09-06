import { describe, it, expect } from "vitest";
import {
  isPortfolioAccount,
  isStockAccount,
  isBankAccount,
  isSyncableAccount,
  isBrokerBalanceAccount,
} from "@/utils/accounts";

describe("isPortfolioAccount", () => {
  it("STOCK으로 시작하는 유형은 true다", () => {
    expect(isPortfolioAccount("STOCK_KIS")).toBe(true);
    expect(isPortfolioAccount("STOCK_KIWOOM")).toBe(true);
    expect(isPortfolioAccount("STOCK_OTHER")).toBe(true);
  });

  it("CASH_OTHER는 true다", () => {
    expect(isPortfolioAccount("CASH_OTHER")).toBe(true);
  });

  it("은행 계좌 유형은 false다", () => {
    expect(isPortfolioAccount("BANK_ACCOUNT")).toBe(false);
    expect(isPortfolioAccount("DEPOSIT")).toBe(false);
  });

  it("기타 유형은 false다", () => {
    expect(isPortfolioAccount("OTHER")).toBe(false);
    expect(isPortfolioAccount("REAL_ESTATE")).toBe(false);
    expect(isPortfolioAccount("")).toBe(false);
  });
});

describe("isStockAccount", () => {
  it("STOCK_TYPES에 포함된 유형은 true다", () => {
    expect(isStockAccount("STOCK_KIS")).toBe(true);
    expect(isStockAccount("STOCK_KIWOOM")).toBe(true);
    expect(isStockAccount("STOCK_OTHER")).toBe(true);
  });

  it("포함되지 않은 유형은 false다", () => {
    expect(isStockAccount("CASH_OTHER")).toBe(false);
    expect(isStockAccount("BANK_ACCOUNT")).toBe(false);
    expect(isStockAccount("")).toBe(false);
  });
});

describe("isBankAccount", () => {
  it("BANK_TYPES에 포함된 유형은 true다", () => {
    expect(isBankAccount("BANK_ACCOUNT")).toBe(true);
    expect(isBankAccount("DEPOSIT")).toBe(true);
    expect(isBankAccount("CASH_OTHER")).toBe(true);
  });

  it("포함되지 않은 유형은 false다", () => {
    expect(isBankAccount("STOCK_KIS")).toBe(false);
    expect(isBankAccount("OTHER")).toBe(false);
    expect(isBankAccount("")).toBe(false);
  });
});

describe("isSyncableAccount", () => {
  it("KIS/키움/토스 API 연동 계좌는 true다", () => {
    expect(isSyncableAccount("KIS_API")).toBe(true);
    expect(isSyncableAccount("KIWOOM_API")).toBe(true);
    expect(isSyncableAccount("TOSS_API")).toBe(true);
  });

  it("수동/기타 data_source는 false다", () => {
    expect(isSyncableAccount("MANUAL")).toBe(false);
    expect(isSyncableAccount("")).toBe(false);
  });
});

describe("isBrokerBalanceAccount", () => {
  it("KIS/키움/토스 증권계좌 유형은 true다", () => {
    expect(isBrokerBalanceAccount("STOCK_KIS")).toBe(true);
    expect(isBrokerBalanceAccount("STOCK_KIWOOM")).toBe(true);
    expect(isBrokerBalanceAccount("STOCK_TOSS")).toBe(true);
  });

  it("그 외 유형은 false다", () => {
    expect(isBrokerBalanceAccount("STOCK_OTHER")).toBe(false);
    expect(isBrokerBalanceAccount("BANK_ACCOUNT")).toBe(false);
    expect(isBrokerBalanceAccount("")).toBe(false);
  });
});
