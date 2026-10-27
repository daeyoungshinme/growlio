export const QUERY_KEYS = {
  dashboard: ["dashboard"] as const,
  // portfolioOverviewBase: invalidateQueries 프리픽스 매칭용 — 계좌 필터(전체/개별) 전 변형 포함
  portfolioOverviewBase: ["portfolio-overview"] as const,
  portfolioOverview: (accountId?: string | null) =>
    ["portfolio-overview", accountId ?? "all"] as const,
  portfolioOverviewLite: ["portfolio-overview", "lite"] as const,
  // indexExposureBase: 무효화 프리픽스 전용 — 계좌 필터(전체/개별) 전 변형 포함
  indexExposureBase: ["index-exposure"] as const,
  indexExposure: (accountId?: string | null) => ["index-exposure", accountId ?? "all"] as const,
  // 포트폴리오 편집기 "지수로 묶기" 제안 — indexExposureBase 하위라 sync·계좌 CUD 무효화를 공유
  indexGroupSuggestions: (accountIds: string[] | null) =>
    ["index-exposure", "group-suggestions", accountIds?.slice().sort().join(",") ?? "all"] as const,
  portfolios: ["portfolios"] as const,
  accounts: ["accounts"] as const,
  accountPositions: (accountId: string) => ["account-positions", accountId] as const,
  transactions: (accountId: string) => ["transactions", accountId] as const,
  transactionsAll: ["transactions", "all"] as const,
  /** 무효화 프리픽스 전용 — 전체(`transactionsAll`·`allTransactions`)와 계좌별(`transactions(id)`)을 함께 지운다 */
  transactionsBase: ["transactions"] as const,
  allTransactions: (year: number) => ["transactions", "all", year] as const,
  // 기간별 매수(계좌관리 › 기간별 매수). periodPurchasesBase는 무효화 프리픽스 전용
  periodPurchasesBase: ["period-purchases"] as const,
  periodPurchases: (
    period: "month" | "year",
    year: number,
    month: number | null,
    accountId?: string | null,
  ) => ["period-purchases", period, year, month ?? 0, accountId ?? "all"] as const,
  trades: ["trades"] as const,
  tradesFor: (accountId: string, ticker: string, market: string) =>
    ["trades", accountId, ticker, market] as const,
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
  challenges: ["challenges"] as const,
  challengeSummary: ["challenges", "summary"] as const,
  settings: ["settings"] as const,
  exchangeRate: ["exchange-rate"] as const,
  exchangeRateAlerts: ["exchange-rate-alerts"] as const,
  stockPriceAlerts: ["stock-price-alerts"] as const,
  rebalancingAlerts: ["rebalancing-alerts"] as const,
  rebalancingAlertBase: ["rebalancing-alert"] as const,
  rebalancingAlert: (portfolioId: string) => ["rebalancing-alert", portfolioId] as const,
  rebalancingAlertsByAccount: (portfolioId: string) =>
    ["rebalancing-alert", portfolioId, "accounts"] as const,
  rebalancingAlertByAccount: (portfolioId: string, accountId: string) =>
    ["rebalancing-alert", portfolioId, "accounts", accountId] as const,
  rebalancingHistory: ["rebalancing-history"] as const,
  /** 실행 1건 상세 — `rebalancingHistory` 프리픽스로 함께 무효화된다 */
  rebalancingExecutionDetail: (executionId: string) =>
    ["rebalancing-history", executionId] as const,
  rebalancingPlans: ["rebalancing-plans"] as const,
  rebalancingPlanPreview: (token: string) => ["rebalancing-plan-preview", token] as const,
  taxSummaryBase: ["tax-summary"] as const,
  taxSummary: (year: number, accountId?: string | null) =>
    ["tax-summary", year, accountId ?? "all"] as const,
  overseasPositionsTaxBase: ["overseas-positions-tax"] as const,
  overseasPositionsTax: (accountId?: string | null) =>
    ["overseas-positions-tax", accountId ?? "all"] as const,
  overseasRealizedBase: ["overseas-realized"] as const,
  overseasRealized: (year: number, accountId?: string | null) =>
    ["overseas-realized", year, accountId ?? "all"] as const,
  isaStatus: ["isa-status"] as const,
  pensionContributionBase: ["pension-contribution"] as const,
  pensionContribution: (year: number) => ["pension-contribution", year] as const,
  taxActionPlan: ["tax-action-plan"] as const,
  allocationHistoryBase: ["allocation-history"] as const,
  allocationHistory: (months: number, accountId?: string | null) =>
    ["allocation-history", months, accountId ?? "all"] as const,
  alertHistory: ["alert-history"] as const,
  insights: ["insights"] as const,
  monthlyOptimization: ["monthly-optimization"] as const,
  /** 유저 단위(전체 보유) 리스크 지표 — 포트폴리오별 조회는 없다 */
  portfolioRisk: ["portfolio-risk"] as const,
  marketSignal: ["market-signal"] as const,
  rebalancingStrategy: (portfolioId: string) => ["rebalancing-strategy", portfolioId] as const,
  rebalancingStrategyBase: ["rebalancing-strategy"] as const,
  driftSummary: ["drift-summary"] as const,
  actionItems: ["action-items"] as const,
  compositeSignalStatus: ["composite-signal-status"] as const,
  goalRecommendationBase: ["goal-recommendation"] as const,
  goalRecommendationOverall: ["goal-recommendation", "overall"] as const,
  goalRecommendationByHorizon: ["goal-recommendation", "by-horizon"] as const,
  goalRecommendationByAge: ["goal-recommendation", "by-age"] as const,
  /** goalRecommendationBase 하위 — 후보 저장 시 `invalidateGoalRecommendationData`로 함께 갱신된다.
   * `signature`는 편집 중 목록의 식별자("saved"면 저장된 목록 기준). */
  candidateOverlap: (signature: string) =>
    ["goal-recommendation", "candidate-overlap", signature] as const,
  // portfolioExpectedMetricsBase: 무효화 프리픽스 전용 — 포트폴리오별 변형 전체
  portfolioExpectedMetricsBase: ["portfolio-expected-metrics"] as const,
  portfolioExpectedMetrics: (portfolioId: string) =>
    ["portfolio-expected-metrics", portfolioId] as const,
  goalFeasibility: (
    goalAmount: number,
    targetYear: number,
    monthlyDepositAmount: number,
    initialAmount: number,
  ) => ["goal-feasibility", goalAmount, targetYear, monthlyDepositAmount, initialAmount] as const,
  inflationSummary: ["inflation-summary"] as const,
  /** QQQ/SPY 전술 배분 국면·제안 비중(포트폴리오별) */
  tacticalStatus: (portfolioId: string) => ["tactical-status", portfolioId] as const,
  /** 무효화 프리픽스 전용 */
  tacticalStatusBase: ["tactical-status"] as const,
  /** 전술 배분 규칙 백테스트(포트폴리오별 비중표 × 기간) */
  tacticalBacktest: (portfolioId: string, years: number) =>
    ["tactical-backtest", portfolioId, years] as const,
  /** 무효화 프리픽스 전용 */
  tacticalBacktestBase: ["tactical-backtest"] as const,
} as const;
