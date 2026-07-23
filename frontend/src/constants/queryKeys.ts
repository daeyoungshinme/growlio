export const QUERY_KEYS = {
  dashboard: ["dashboard"] as const,
  // portfolioOverviewBase: invalidateQueries 프리픽스 매칭용 — 계좌 필터(전체/개별) 전 변형 포함
  portfolioOverviewBase: ["portfolio-overview"] as const,
  portfolioOverview: (accountId?: string | null) =>
    ["portfolio-overview", accountId ?? "all"] as const,
  portfolioOverviewLite: ["portfolio-overview", "lite"] as const,
  portfolios: ["portfolios"] as const,
  accounts: ["accounts"] as const,
  accountPositions: (accountId: string) => ["account-positions", accountId] as const,
  transactions: (accountId: string) => ["transactions", accountId] as const,
  transactionsAll: ["transactions", "all"] as const,
  allTransactions: (year: number) => ["transactions", "all", year] as const,
  dividendByTickerBase: ["dividend-by-ticker"] as const,
  dividendByTicker: (accountId?: string | null) =>
    ["dividend-by-ticker", accountId ?? "all"] as const,
  dividendSummaryBase: ["dividend-summary"] as const,
  dividendSummary: (accountId?: string | null) => ["dividend-summary", accountId ?? "all"] as const,
  dividendPositionsBase: ["dividend-positions"] as const,
  dividendPositions: (accountId?: string | null) =>
    ["dividend-positions", accountId ?? "all"] as const,
  dcaAnalysis: ["dca-analysis"] as const,
  dividendPlan: ["dividend-plan"] as const,
  settings: ["settings"] as const,
  exchangeRate: ["exchange-rate"] as const,
  exchangeRateAlerts: ["exchange-rate-alerts"] as const,
  stockPriceAlerts: ["stock-price-alerts"] as const,
  rebalancingAlerts: ["rebalancing-alerts"] as const,
  rebalancingAlert: (portfolioId: string) => ["rebalancing-alert", portfolioId] as const,
  rebalancingAlertsByAccount: (portfolioId: string) =>
    ["rebalancing-alert", portfolioId, "accounts"] as const,
  rebalancingAlertByAccount: (portfolioId: string, accountId: string) =>
    ["rebalancing-alert", portfolioId, "accounts", accountId] as const,
  rebalancingHistory: ["rebalancing-history"] as const,
  rebalancingPlans: ["rebalancing-plans"] as const,
  taxSummaryBase: ["tax-summary"] as const,
  taxSummary: (year: number, accountId?: string | null) =>
    ["tax-summary", year, accountId ?? "all"] as const,
  overseasPositionsTaxBase: ["overseas-positions-tax"] as const,
  overseasPositionsTax: (accountId?: string | null) =>
    ["overseas-positions-tax", accountId ?? "all"] as const,
  isaStatus: ["isa-status"] as const,
  pensionContribution: (year: number) => ["pension-contribution", year] as const,
  allocationHistoryBase: ["allocation-history"] as const,
  allocationHistory: (months: number, accountId?: string | null) =>
    ["allocation-history", months, accountId ?? "all"] as const,
  alertHistory: ["alert-history"] as const,
  insights: ["insights"] as const,
  monthlyOptimization: ["monthly-optimization"] as const,
  portfolioRisk: (id?: string) => ["portfolio-risk", id] as const,
  marketSignal: ["market-signal"] as const,
  rebalancingStrategy: (portfolioId: string) => ["rebalancing-strategy", portfolioId] as const,
  driftSummary: ["drift-summary"] as const,
  compositeSignalStatus: ["composite-signal-status"] as const,
  goalRecommendationOverall: ["goal-recommendation", "overall"] as const,
  goalRecommendationByHorizon: ["goal-recommendation", "by-horizon"] as const,
  portfolioExpectedMetrics: (portfolioId: string) =>
    ["portfolio-expected-metrics", portfolioId] as const,
  goalFeasibility: (
    goalAmount: number,
    targetYear: number,
    monthlyDepositAmount: number,
    initialAmount: number,
  ) => ["goal-feasibility", goalAmount, targetYear, monthlyDepositAmount, initialAmount] as const,
  inflationSummary: ["inflation-summary"] as const,
} as const;
