/**
 * 자산·계획·알림 설정 페이지 딥링크 — 탭 이름은 `constants/tabs.ts` 유니온으로만 받는다(plans/107 C1).
 * 탭 이름을 바꾸면 여기서 컴파일 에러가 나 링크가 조용히 깨지지 않는다. 리밸런싱은 `rebalancingUrl.ts`.
 *
 * 값은 인코딩하지 않는다 — 전부 `&`·`=`·`#`가 없는 상수이고, 이메일·푸시·백엔드 링크가 쓰는 문자열과
 * 같은 모양(`/invest-plan?tab=적립 계획`)을 유지하려는 것. 공백·한글은 브라우저·라우터가 처리한다.
 */
import {
  MARKET_ALERT_SECTION,
  type AccountHistorySegment,
  type AlertTab,
  type AssetManagementTab,
  type InvestPlanTab,
  type PortfolioTab,
  type TaxTab,
} from "@/constants/tabs";

function withQuery(path: string, params: Record<string, string | undefined>): string {
  const query = Object.entries(params)
    .filter((entry): entry is [string, string] => entry[1] !== undefined)
    .map(([key, value]) => `${key}=${value}`)
    .join("&");
  return query ? `${path}?${query}` : path;
}

/** 자산 › 투자현황(`portfolioTab` 하위 탭) */
export function portfolioUrl(portfolioTab?: PortfolioTab, divTab?: "월별 배당"): string {
  return withQuery("/assets", { tab: "투자현황", portfolioTab, divTab });
}

/** 자산 › 계좌관리(`atab`), 내역 탭이면 `history` 세그먼트까지 */
export function assetManagementUrl(
  atab?: AssetManagementTab,
  history?: AccountHistorySegment,
): string {
  return withQuery("/assets", { tab: "계좌관리", atab, history });
}

/** 계획 페이지 — `from=recommendation`은 추천 화면에서 넘어왔다는 표시(적립 계획 안내 문구용) */
export function investPlanUrl(
  tab: InvestPlanTab,
  options: { taxTab?: TaxTab; from?: "recommendation" } = {},
): string {
  return withQuery("/invest-plan", { tab, taxTab: options.taxTab, from: options.from });
}

/** 설정 › 알림 설정 — `MARKET_ALERT_SECTION`은 탭이 아니라 시장 모니터링 카드를 펼치는 값 */
export function notificationSettingsUrl(atab?: AlertTab | typeof MARKET_ALERT_SECTION): string {
  return withQuery("/settings/notifications", { atab });
}
