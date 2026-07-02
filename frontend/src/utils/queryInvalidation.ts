import type { QueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";

/** 계좌 sync 후 — portfolio + dashboard + 배당 데이터 + 인사이트 + 드리프트 */
export function invalidateSyncData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverview }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverviewLite }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendByTicker }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendSummary }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.insights }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioRisk() }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.driftSummary }),
  ]);
}

/** 계좌 CUD 후 — accounts + portfolio + dashboard */
export function invalidateAccountData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.accounts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverview }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverviewLite }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
  ]);
}

/** 거래내역 CUD 후 — transactions + dashboard */
export function invalidateTransactionData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.transactionsAll }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
  ]);
}

/** 포트폴리오/백테스트/리밸런싱 CUD 후 */
export function invalidatePortfolioData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolios }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.accounts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.driftSummary }),
  ]);
}

/** DCA 목표 변경 후 — dca-analysis + settings + dashboard + dividend-plan */
export function invalidateDcaData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dcaAnalysis }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendPlan }),
  ]);
}

/** 배당 계획 목표 변경 후 */
export function invalidateDividendPlanData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendPlan });
}

/** 환율 알림 CUD 후 */
export function invalidateAlertData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.exchangeRateAlerts });
}

/** 주가 알림 CUD 후 */
export function invalidateStockPriceAlertData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.stockPriceAlerts });
}

/** 리밸런싱 알림 CUD 후 */
export function invalidateRebalancingAlertData(qc: QueryClient, portfolioId: string) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlerts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlert(portfolioId) }),
  ]);
}

/** 리밸런싱 주문 실행 후 — 실행 이력 */
export function invalidateRebalancingHistoryData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingHistory });
}
