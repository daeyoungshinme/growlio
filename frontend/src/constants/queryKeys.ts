export const QUERY_KEYS = {
  dashboard: ["dashboard"] as const,
  portfolioOverview: ["portfolio-overview"] as const,
  portfolios: ["portfolios"] as const,
  accounts: ["accounts"] as const,
  accountPositions: (accountId: string) => ["account-positions", accountId] as const,
  transactions: (accountId: string) => ["transactions", accountId] as const,
  allTransactions: (year: number) => ["transactions", "all", year] as const,
  dividendByTicker: ["dividend-by-ticker"] as const,
  dividendSummary: ["dividend-summary"] as const,
  exchangeRate: ["exchange-rate"] as const,
} as const;
