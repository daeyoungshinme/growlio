export const ASSET_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "통장잔고",
  DEPOSIT: "예금/적금",
  STOCK_KIS: "주식 (KIS)",
  STOCK_KIWOOM: "주식 (키움)",
  STOCK_OTHER: "주식 (타증권사)",
  CASH_OTHER: "예수금 (기타)",
  CASH_STOCK: "예수금 (증권계좌)",
  OTHER: "기타",
  REAL_ESTATE: "부동산",
};

export const STOCK_TYPE_LABELS: Record<string, string> = {
  STOCK_KIS: "KIS",
  STOCK_KIWOOM: "키움",
  STOCK_OTHER: "타증권사",
  CASH_OTHER: "예수금",
};

export const DATA_SOURCE_LABELS: Record<string, string> = {
  MANUAL: "수동",
  KIS_API: "KIS 자동",
  KIWOOM_API: "키움 자동",
  OPEN_BANKING: "오픈뱅킹",
};

export const DATA_SOURCE_BADGE: Record<string, string> = {
  KIS_API: "bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400",
  KIWOOM_API: "bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400",
  OPEN_BANKING: "bg-green-50 dark:bg-green-950 text-green-600 dark:text-green-400",
  MANUAL: "bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400",
};

export const BANK_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "입출금",
  DEPOSIT: "예·적금",
  CASH_OTHER: "현금/기타",
};

export const STOCK_TYPES: string[] = ["STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER"];
export const BANK_TYPES: string[] = ["BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER"];
export const REAL_ESTATE_TYPES: string[] = ["REAL_ESTATE"];

export { DOMESTIC_MARKETS } from "./markets";
export { SEARCH_DROPDOWN_HIDE_DELAY, REDIRECT_DELAY_MS, FOCUS_SETTLE_DELAY } from "./timers";
