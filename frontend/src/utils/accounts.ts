import {
  STOCK_TYPES,
  BANK_TYPES,
  SYNCABLE_DATA_SOURCES,
  ORDER_EXECUTABLE_ASSET_TYPES,
  BROKER_BALANCE_ASSET_TYPES,
} from "@/constants";
import type { AccountRow } from "@/types";

/** 주식 계좌 포트폴리오 뷰에 포함되는 계좌 유형 (예수금 포함) */
export function isPortfolioAccount(assetType: string): boolean {
  return assetType.startsWith("STOCK") || assetType === "CASH_OTHER";
}

/** 투자기간별 자산현황 집계 대상: 투자기간 태그가 있는 증권 계좌만. 은행·부동산 계좌도 태그할 수 있지만
 * 이 집계는 "주식 총평가액" 아래에 붙으므로 같은 범위(백엔드 portfolio_service.STOCK_TYPES)로 맞춘다. */
export function horizonTaggedAccounts(accounts: AccountRow[]): AccountRow[] {
  return accounts.filter((a) => a.investment_horizon && isPortfolioAccount(a.asset_type));
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
  return BROKER_BALANCE_ASSET_TYPES.includes(assetType);
}

/** 리밸런싱 주문을 실제로 실행할 수 있는 브로커 계좌인지 판별 (account.asset_type 전달).
 *  토스 제외 — 주문 API 미구현이라 잔고/진단(`isBrokerBalanceAccount`)까지만 지원. */
export function isOrderExecutableAccount(assetType: string): boolean {
  return ORDER_EXECUTABLE_ASSET_TYPES.includes(assetType);
}
