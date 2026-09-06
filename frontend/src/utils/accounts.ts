import { STOCK_TYPES, BANK_TYPES, SYNCABLE_DATA_SOURCES } from "@/constants";

/** 주식 계좌 포트폴리오 뷰에 포함되는 계좌 유형 (예수금 포함) */
export function isPortfolioAccount(assetType: string): boolean {
  return assetType.startsWith("STOCK") || assetType === "CASH_OTHER";
}

/** KIS/키움/토스/기타 증권계좌 유형인지 판별 */
export function isStockAccount(assetType: string): boolean {
  return STOCK_TYPES.includes(assetType);
}

/** 은행계좌/예금/예수금 유형인지 판별 */
export function isBankAccount(assetType: string): boolean {
  return BANK_TYPES.includes(assetType);
}

/** KIS/키움/토스 API 연동 계좌라 브로커 동기화가 가능한지 판별 (account.data_source 전달) */
export function isSyncableAccount(dataSource: string): boolean {
  return SYNCABLE_DATA_SOURCES.includes(dataSource);
}

/** 실시간 잔고 조회·리밸런싱 진단 대상 브로커 계좌 유형인지 판별 (account.asset_type 전달).
 *  주문 실행은 별개 — 토스는 주문 API 미구현이라 실행 경로는 KIS/키움만. */
export function isBrokerBalanceAccount(assetType: string): boolean {
  return assetType === "STOCK_KIS" || assetType === "STOCK_KIWOOM" || assetType === "STOCK_TOSS";
}
