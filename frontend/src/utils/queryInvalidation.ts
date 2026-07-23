import type { QueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";

/** 계좌 sync 후 — portfolio + dashboard + 배당 데이터 + 인사이트 + 드리프트 */
export function invalidateSyncData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverviewBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendByTickerBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendPositionsBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.overseasPositionsTaxBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.allocationHistoryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.insights }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioRisk() }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.driftSummary }),
  ]);
}

/** 계좌 CUD 후 — accounts + portfolio + dashboard + transactions
 * (현금성 계좌 잔액 수정 시 백엔드가 입출금 거래를 자동 생성할 수 있음) */
export function invalidateAccountData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.accounts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolioOverviewBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.transactionsAll }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.isaStatus }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendByTickerBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendPositionsBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.overseasPositionsTaxBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.allocationHistoryBase }),
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
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlertsByAccount(portfolioId) }),
  ]);
}

/** 리밸런싱 주문 실행 후 — 실행 이력 */
export function invalidateRebalancingHistoryData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingHistory });
}

/** 리밸런싱 대기 플랜 취소/승인 후 — 대기 플랜 목록 + 실행 이력(승인 시 새 이력 생성) */
export function invalidateRebalancingPlanData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingPlans }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingHistory }),
  ]);
}

/** 복합신호(시장/리스크) 알림 수신 여부 설정 변경 후 */
export function invalidateCompositeSignalData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.compositeSignalStatus }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
  ]);
}

/** 시장신호 매일 요약 알림 수신 여부 설정 변경 후 */
export function invalidateMarketSignalDigestData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
}

/** 연말 절세 리마인더 수신 여부 설정 변경 후 */
export function invalidateYearEndTaxReminderData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
}

/** 목표 달성 알림(자산/입금/배당) 수신 여부 설정 변경 후 */
export function invalidateGoalAchievementAlertsData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
}

/** 월간 리포트 수신 여부 설정 변경 후 */
export function invalidateMonthlyReportAlertsData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
}

/** 추천 비중 변화 알림 수신 여부 설정 변경 후 */
export function invalidateRecommendationDriftAlertData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
}

/** 목표 역산 추천 후보 ETF/추천 엔진 설정(리스크성향·최대비중·CAGR기간) 변경 후 —
 * 포트폴리오별/전체 추천 전부(접두사 매칭) + settings 무효화 */
export function invalidateGoalRecommendationData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: ["goal-recommendation"] }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
  ]);
}
