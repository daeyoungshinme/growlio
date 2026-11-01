// URL 쿼리(`?tab=`·`?atab=`·`?taxTab=`·`?history=`)에 실리는 탭 이름의 단일 정의.
// 백엔드가 링크 문자열로 같은 이름을 쓴다(`action_items_service`·`tax/tax_action_service`·이메일·푸시 딥링크) —
// 이름을 바꾸면 백엔드 링크와 `utils/legacyTabRedirect.ts`도 함께 맞출 것. 링크는 `utils/tabUrl.ts` 빌더로(리밸런싱은 `utils/rebalancingUrl.ts`).

/** 자산 › 계좌관리(`?atab=`). 첫 항목이 기본 탭 — 투자 흐름의 중심인 증권계좌 */
export const ASSET_MANAGEMENT_TABS = ["증권계좌", "은행계좌", "부동산", "내역"] as const;
export type AssetManagementTab = (typeof ASSET_MANAGEMENT_TABS)[number];

/** 자산 › 계좌관리 › 내역(`?history=`) */
export const ACCOUNT_HISTORY_SEGMENTS = ["현금 흐름", "매수 내역"] as const;
export type AccountHistorySegment = (typeof ACCOUNT_HISTORY_SEGMENTS)[number];

export const PORTFOLIO_TABS = ["종목 현황", "배당"] as const;
export type PortfolioTab = (typeof PORTFOLIO_TABS)[number];

export const ASSETS_TOP_TABS = ["투자현황", "계좌관리"] as const;
export type AssetsTopTab = (typeof ASSETS_TOP_TABS)[number];

/** 계획(`/invest-plan?tab=`) */
export const INVEST_PLAN_TABS = ["적립 계획", "배당 계획", "절세", "챌린지"] as const;
export type InvestPlanTab = (typeof INVEST_PLAN_TABS)[number];

/** 계획 › 절세(`?taxTab=`) */
export const TAX_TABS = ["한도 현황", "세금 추정"] as const;
export type TaxTab = (typeof TAX_TABS)[number];

/** 설정 › 알림 설정(`/settings/notifications?atab=`) */
export const ALERT_TABS = ["환율 알림", "주가 알림", "발송 이력"] as const;
export type AlertTab = (typeof ALERT_TABS)[number];

/** 알림 설정 `?atab=`의 특수값 — 탭이 아니라 "시장 모니터링" 카드를 펼친 채 연다(발송된 링크 호환으로 유지) */
export const MARKET_ALERT_SECTION = "시장 신호 알림";
