export const ASSET_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "통장잔고",
  DEPOSIT: "예금/적금",
  STOCK_KIS: "주식 (KIS)",
  STOCK_KIWOOM: "주식 (키움)",
  STOCK_TOSS: "주식 (토스)",
  STOCK_OTHER: "주식 (타증권사)",
  CASH_OTHER: "예수금 (기타)",
  CASH_STOCK: "예수금 (증권계좌)",
  OTHER: "기타",
  REAL_ESTATE: "부동산",
};

export const STOCK_TYPE_LABELS: Record<string, string> = {
  STOCK_KIS: "KIS",
  STOCK_KIWOOM: "키움",
  STOCK_TOSS: "토스",
  STOCK_OTHER: "타증권사",
  CASH_OTHER: "예수금",
};

export const BANK_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "입출금",
  DEPOSIT: "예·적금",
  CASH_OTHER: "현금/기타",
};

export const STOCK_TYPES: string[] = ["STOCK_KIS", "STOCK_KIWOOM", "STOCK_TOSS", "STOCK_OTHER"];
/** 리밸런싱 주문을 실제로 실행할 수 있는 브로커 계좌 asset_type — 토스 제외(주문 API 미구현).
 * 백엔드 order_builder.ORDER_EXECUTABLE_ASSET_TYPES와 동일 집합 유지. */
export const ORDER_EXECUTABLE_ASSET_TYPES: string[] = ["STOCK_KIS", "STOCK_KIWOOM"];
export const BANK_TYPES: string[] = ["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER", "CASH_STOCK"];
/** 브로커 API 연동으로 데이터 동기화가 가능한 data_source 값 */
export const SYNCABLE_DATA_SOURCES: string[] = ["KIS_API", "KIWOOM_API", "TOSS_API"];
export const REAL_ESTATE_TYPES: string[] = ["REAL_ESTATE"];

export { DOMESTIC_MARKETS } from "./markets";
