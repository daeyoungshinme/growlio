import type { QueryClient } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";

// actionItems(홈 "지금 할 일")는 드리프트·예수금·세금·챌린지·알림 설정을 모두 읽으므로 그 원천 무효화 함수마다 함께 지운다.

/** 보유 구성(포지션·예수금·계좌 목록)을 읽는 쿼리 — sync와 계좌·포지션 CUD가 함께 지운다.
 * 두 함수가 목록을 따로 들고 있으면 새 키를 한쪽에만 넣는 누락이 생긴다(plans/113 B3). */
const HOLDINGS_QUERY_KEYS = [
  QUERY_KEYS.accounts,
  QUERY_KEYS.accountPositionsBase,
  QUERY_KEYS.portfolioOverviewBase,
  QUERY_KEYS.indexExposureBase,
  // 기간별 매수 추정은 스냅샷 포지션 기준
  QUERY_KEYS.periodPurchasesBase,
  QUERY_KEYS.dashboard,
  QUERY_KEYS.dividendByTickerBase,
  QUERY_KEYS.dividendSummaryBase,
  QUERY_KEYS.dividendPositionsBase,
  QUERY_KEYS.dividendPlan,
  // 배당 약한 달 추천은 보유 종목 배당 요약으로 계산한다
  QUERY_KEYS.monthlyOptimization,
  QUERY_KEYS.taxSummaryBase,
  QUERY_KEYS.overseasPositionsTaxBase,
  QUERY_KEYS.overseasRealizedBase,
  QUERY_KEYS.taxActionPlan,
  QUERY_KEYS.isaStatus,
  QUERY_KEYS.allocationHistoryBase,
  // 보유 기반 카드 — 포지션 수동 저장·계좌 삭제도 보유 구성을 바꾼다(plans/95 F1)
  QUERY_KEYS.insights,
  QUERY_KEYS.portfolioRisk,
  QUERY_KEYS.driftSummary,
  // 목표 역산 추천·후보 중복 점검("보유 중" 표시)이 보유 포지션 기준 — 백엔드 sync도 같은 캐시를 지운다
  QUERY_KEYS.goalRecommendationBase,
  // 환전 계획의 보유 달러는 계좌 deposit_usd 합 (plans/97 B2)
  QUERY_KEYS.fxPlanBase,
  QUERY_KEYS.actionItems,
  // 자산 합계 기준 카드 — 백엔드 sync도 같은 캐시를 지운다 (plans/110 D4)
  QUERY_KEYS.dcaAnalysis,
  QUERY_KEYS.challenges,
] as const;

function invalidateKeys(qc: QueryClient, keys: readonly (readonly unknown[])[]) {
  return Promise.all(keys.map((queryKey) => qc.invalidateQueries({ queryKey })));
}

/** 계좌 sync 후 — 보유 기반 쿼리 전부(계좌 last_synced_at·예수금 포함) */
export function invalidateSyncData(qc: QueryClient) {
  return invalidateKeys(qc, HOLDINGS_QUERY_KEYS);
}

/** 계좌 CUD 후 — 보유 기반 쿼리 + 거래내역(현금성 계좌 잔액 수정 시 백엔드가 입출금 거래를 자동 생성할 수 있음)
 * + 연금 납입 현황(연금·IRP 계좌 추가/삭제·tax_type 변경) */
export function invalidateAccountData(qc: QueryClient) {
  return invalidateKeys(qc, [
    ...HOLDINGS_QUERY_KEYS,
    QUERY_KEYS.transactionsBase,
    QUERY_KEYS.pensionContributionBase,
  ]);
}

/** 계좌 브로커 API 키 삭제(연동 해제) 후 — 계좌 데이터 + 리밸런싱 알림/대기 플랜
 * (자동 매매 가능 여부가 바뀌므로 리밸런싱 화면이 해제된 계좌를 거래가능으로 계속 표시하지 않게) */
export function invalidateBrokerCredentialData(qc: QueryClient) {
  return Promise.all([
    invalidateAccountData(qc),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlerts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlertBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingPlans }),
  ]);
}

/** 거래내역 CUD 후 — transactions + dashboard + 적립 챌린지(입금이 스트릭에 영향)
 * + 연금/ISA 납입 현황·절세 액션 플랜(입금·배당 내역 기준 집계)
 * + 배당 요약·배당 계획(수령 배당은 DIVIDEND 거래 기준 — 백엔드도 거래 변경 시 배당 캐시를 지운다) */
export function invalidateTransactionData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.transactionsBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.challenges }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.pensionContributionBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.isaStatus }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxActionPlan }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendByTickerBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendPlan }),
  ]);
}

/** 수기 매매 기록 CUD 후 — 기록 목록 + 기간별 매수 현황(수기 기록이 추정을 대체)
 * + 해외 SELL 기록이 미지원 계좌 실현손익이 되므로 양도세 요약·절세 액션·지금 할 일 */
export function invalidateTradeData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.trades }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.periodPurchasesBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.overseasRealizedBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxSummaryBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxActionPlan }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    // 백엔드도 매매 기록 CUD에서 인사이트 캐시를 지운다(실현손익 기반 카드, plans/117 B4·118 C5)
    qc.invalidateQueries({ queryKey: QUERY_KEYS.insights }),
  ]);
}

/** 적립 챌린지 CUD 후 — challenges(+summary 프리픽스 매칭) + dashboard */
export function invalidateChallengeData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.challenges }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    // 첫 챌린지를 만들면 백엔드가 리마인더 설정을 켠다 — 토글이 꺼진 채로 남지 않게
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
  ]);
}

/** DART API 키 저장·삭제 후 — 설정 + 국내 종목 배당(DPS)을 쓰는 쿼리. 백엔드도 같은 시점에 배당 캐시를 지운다
 * (plans/117 B1). 프론트 배당 쿼리는 staleTime이 1시간이라 함께 지우지 않으면 키를 넣어도 DPS 0이 남는다(plans/118 C2). */
export function invalidateDartKeyData(qc: QueryClient) {
  return invalidateKeys(qc, [
    QUERY_KEYS.settings,
    QUERY_KEYS.dividendSummaryBase,
    QUERY_KEYS.dividendByTickerBase,
    QUERY_KEYS.dividendPositionsBase,
    QUERY_KEYS.dividendPlan,
    QUERY_KEYS.monthlyOptimization,
  ]);
}

/** settings 단일 재조회 — 다른 화면 데이터에 영향이 없는 설정 저장 후, 또는 백엔드가 설정을 바꿨을 수 있을 때 */
export function invalidateSettingsData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });
}

/** 포트폴리오/백테스트/리밸런싱 CUD 후 */
export function invalidatePortfolioData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.portfolios }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.accounts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.driftSummary }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingStrategyBase }),
    // 환전 계획은 목표 비중의 해외 몫·연결 계좌를 읽는다 (plans/97 B2)
    qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    // 알림 목록은 포트폴리오 이름을, 기대지표 미리보기는 목표 비중을 담는다 (plans/62 C2·77 C2).
    // stale 표시만 한다 — 적용 직후 확인창이 열린 채 무거운 기대지표 재계산을 기다리지 않게(다음 마운트 때 조회)
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlerts, refetchType: "none" }),
    qc.invalidateQueries({
      queryKey: QUERY_KEYS.portfolioExpectedMetricsBase,
      refetchType: "none",
    }),
  ]);
}

/** 전술 배분 설정 변경 후 — 국면 상태 + 백테스트(비중표가 바뀌면 결과도 바뀜) + 홈 "지금 할 일"(전술 적용 항목).
 * 제안 비중 적용 시엔 포트폴리오 목표가 바뀌므로 `invalidatePortfolioData`도 함께(포트폴리오 목록·드리프트·리밸런싱 전략). */
export function invalidateTacticalData(
  qc: QueryClient,
  opts: { portfolioChanged?: boolean; alertsReset?: boolean } = {},
) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.tacticalStatusBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.tacticalBacktestBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    ...(opts.portfolioChanged ? [invalidatePortfolioData(qc)] : []),
    // 전술을 끄면 서버가 그 포트폴리오의 TACTICAL 알림을 모두 일반 모드로 되돌린다 — 포트폴리오·계좌별 알림 캐시까지
    // 비워야 모달이 옛 TACTICAL 값을 다시 저장하지 않는다 (plans/99 B2). 환전 계획 기본 포트폴리오도 이 알림을 따른다
    ...(opts.alertsReset
      ? [
          qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlerts }),
          qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingAlertBase }),
          qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase }),
        ]
      : []),
  ]);
}

/** DCA 목표 변경 후 — dca-analysis + settings + dashboard + dividend-plan + 적립 챌린지(수익률/평가금액 진행률 기준값 변경) + 환전 계획(월 적립액 기준) */
export function invalidateDcaData(qc: QueryClient, opts: { goalRecommendation?: boolean } = {}) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dcaAnalysis }),
    // 목표 금액·연도가 추천 결과도 바꿀 때 — settings는 여기서 이미 무효화하므로 invalidateGoalRecommendationData를 따로 부르지 않는다
    ...(opts.goalRecommendation
      ? [qc.invalidateQueries({ queryKey: QUERY_KEYS.goalRecommendationBase })]
      : []),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dashboard }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.dividendPlan }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.challenges }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
  ]);
}

/** 환율 알림 CUD 후 */
export function invalidateAlertData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.exchangeRateAlerts });
}

/**
 * 추가 환전 항목(여행 등) CUD·구간 알림 맞추기 후 — 항목 삭제는 서버가 그 알림도 지운다.
 * 보관 계좌를 지정한 항목은 적립 환전 계획의 보유 달러를 바꾸므로 그 계획도 다시 받는다
 */
export function invalidateFxExtraNeedData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.fxExtraNeeds }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.exchangeRateAlerts }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
  ]);
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
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    // 환전 계획의 기본 포트폴리오는 적립 자동매수 알림을 따른다 (plans/97 B2)
    qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase }),
    // drift-summary의 "알림 설정됨"·이탈 기준이 알림 설정을 따른다 — 저장 후 "알림 미설정"이 남던 문제 (plans/62 C1)
    qc.invalidateQueries({ queryKey: QUERY_KEYS.driftSummary }),
  ]);
}

/** 리밸런싱 주문 실행 후 — 실행 이력 */
export function invalidateRebalancingHistoryData(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingHistory });
}

/** 리밸런싱 대기 플랜 취소/승인 후 — 대기 플랜 목록 + 실행 이력(승인 시 새 이력 생성).
 * 승인은 즉시 체결하므로(`status === "EXECUTED"`) 수동 실행 경로처럼 보유·드리프트·지금 할 일까지 갱신한다. */
export function invalidateRebalancingPlanData(qc: QueryClient, opts: { executed?: boolean } = {}) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingPlans }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.rebalancingHistory }),
    // 환전 대기 leg의 재개·건너뛰기·만료는 홈 "다시 매수" 행과 환전 계획의 "지금" 구간을 바꾼다 — 실행이
    // 아니어도 함께 갱신한다(plans/122 C4)
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.fxPlanBase }),
    ...(opts.executed ? [invalidateSyncData(qc)] : []),
  ]);
}

/** 복합신호(시장/리스크) 알림 수신 여부 설정 변경 후 */
export function invalidateCompositeSignalData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.compositeSignalStatus }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
  ]);
}

/** 목표 역산 추천 후보 ETF/추천 엔진 설정(리스크성향·최대비중·CAGR기간) 변경 후 —
 * 포트폴리오별/전체 추천 전부(접두사 매칭) + settings 무효화 */
export function invalidateGoalRecommendationData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.goalRecommendationBase }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
  ]);
}

/** 소득 구간(연금 세액공제율) 변경 후 — 절세 액션 플랜 + settings */
export function invalidateIncomeBracketData(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: QUERY_KEYS.taxActionPlan }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.settings }),
    qc.invalidateQueries({ queryKey: QUERY_KEYS.actionItems }),
  ]);
}
