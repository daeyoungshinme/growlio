export const DOMESTIC_MARKETS: string[] = ["KOSPI", "KOSDAQ", "KRX"];

/** 포지션 편집 마켓 드롭다운용 — KRX·_US 변형 제외 */
export const POSITION_MARKETS = ["KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "AMEX"] as const;
export const OVERSEAS_MARKETS: string[] = [
  "NYSE",
  "NASDAQ",
  "AMEX",
  "NYSE_US",
  "NASDAQ_US",
  "AMEX_US",
];

export const OVERSEAS_MARKET_SET = new Set<string>(OVERSEAS_MARKETS);

export function isOverseasMarket(market: string): boolean {
  return OVERSEAS_MARKET_SET.has(market.toUpperCase());
}
