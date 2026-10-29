export const DOMESTIC_MARKETS: string[] = ["KOSPI", "KOSDAQ", "KRX"];

/** 포지션 편집 마켓 드롭다운용 — KRX·_US 변형 제외 */
export const POSITION_MARKETS = ["KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "AMEX"] as const;
/** 백엔드 `app/constants.py::OVERSEAS_MARKETS`와 같은 집합(+ `_US` 변형) — 빠지면 그 시장 종목을 국내로 판정한다 */
export const OVERSEAS_MARKETS: string[] = [
  "NYSE",
  "NASDAQ",
  "AMEX",
  "NYSE_US",
  "NASDAQ_US",
  "AMEX_US",
  "TSE",
  "HKEX",
  "SSE",
  "SGX",
  "LSE",
];

export const OVERSEAS_MARKET_SET = new Set<string>(OVERSEAS_MARKETS);

export function isOverseasMarket(market: string): boolean {
  return OVERSEAS_MARKET_SET.has(market.toUpperCase());
}

/** 화면 표시용 시장 라벨 — 내부 변형 코드(`_US` 접미사·"US" 센티널·KRX·CASH)가 그대로 보이지 않게 한다.
 * 사용자에게 익숙한 거래소명(KOSPI·NASDAQ 등)은 그대로 둔다 (docs/plans/67). */
const MARKET_DISPLAY_LABEL: Record<string, string> = {
  NYSE_US: "NYSE",
  NASDAQ_US: "NASDAQ",
  AMEX_US: "AMEX",
  US: "미국",
  KRX: "국내",
  CASH: "현금",
};

export function marketLabel(market: string | null | undefined): string {
  if (!market) return "";
  return MARKET_DISPLAY_LABEL[market.toUpperCase()] ?? market;
}
