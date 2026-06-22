import { STOCK_TYPES, BANK_TYPES } from "@/constants";

/** 주식 계좌 포트폴리오 뷰에 포함되는 계좌 유형 (예수금 포함) */
export function isPortfolioAccount(assetType: string): boolean {
  return assetType.startsWith("STOCK") || assetType === "CASH_OTHER";
}

/** KIS/키움/기타 증권계좌 유형인지 판별 */
export function isStockAccount(assetType: string): boolean {
  return STOCK_TYPES.includes(assetType);
}

/** 은행계좌/예금/예수금 유형인지 판별 */
export function isBankAccount(assetType: string): boolean {
  return BANK_TYPES.includes(assetType);
}
