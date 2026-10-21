/**
 * 리밸런싱 페이지 URL 상태 — 탭(rtab)·목표 조정 모드(gmode)·딥링크 파라미터의 단일 정의(plans/64 S1).
 * 링크를 만드는 곳은 문자열을 직접 조립하지 말고 rebalancingUrl()을 쓴다.
 */

export const REBALANCING_TABS = ["진단", "포트폴리오", "목표 조정", "이력"] as const;
export type RebalancingTab = (typeof REBALANCING_TABS)[number];

/** 목표 조정 탭 안의 모드 — 둘 다 "목표 비중 자체를 바꾸는 제안"이라 한 탭에 묶었다 */
export const GOAL_MODES = ["추천", "전술"] as const;
export type GoalMode = (typeof GOAL_MODES)[number];

const DEFAULT_TAB: RebalancingTab = "진단";
const DEFAULT_GOAL_MODE: GoalMode = "추천";

function isTab(value: string | null): value is RebalancingTab {
  return REBALANCING_TABS.includes(value as RebalancingTab);
}

function isGoalMode(value: string | null): value is GoalMode {
  return GOAL_MODES.includes(value as GoalMode);
}

/**
 * URL에서 탭·모드를 읽는다. 예전 탭 값 `rtab=추천`/`rtab=전술`은 이미 발송된 이메일·푸시 링크가
 * 있으므로 계속 목표 조정 탭의 해당 모드로 연다. 알 수 없는 값은 진단.
 */
export function parseRebalancingTab(params: URLSearchParams): {
  tab: RebalancingTab;
  mode: GoalMode;
} {
  const rawTab = params.get("rtab");
  const rawMode = params.get("gmode");
  if (isGoalMode(rawTab)) return { tab: "목표 조정", mode: rawTab };
  return {
    tab: isTab(rawTab) ? rawTab : DEFAULT_TAB,
    mode: isGoalMode(rawMode) ? rawMode : DEFAULT_GOAL_MODE,
  };
}

export interface RebalancingUrlOptions {
  tab?: RebalancingTab;
  mode?: GoalMode;
  portfolioId?: string | null;
  /** "1" = 알림 설정 모달, "dca" = 정기 적립식 프리셋 */
  openAlert?: "1" | "dca";
  openExecution?: boolean;
  openRecOptions?: boolean;
}

/** URLSearchParams에 탭·딥링크 값을 덮어쓴다(지정한 키만). 페이지 내 setSearchParams와 링크 빌더가 공유. */
export function applyRebalancingParams(
  params: URLSearchParams,
  { tab, mode, portfolioId, openAlert, openExecution, openRecOptions }: RebalancingUrlOptions,
): URLSearchParams {
  if (tab) {
    params.set("rtab", tab);
    if (tab !== "목표 조정") params.delete("gmode");
  }
  if (mode) params.set("gmode", mode);
  if (portfolioId) params.set("portfolioId", portfolioId);
  if (openAlert) params.set("openAlert", openAlert);
  if (openExecution) params.set("openExecution", "1");
  if (openRecOptions) params.set("openRecOptions", "1");
  return params;
}

/** 리밸런싱 페이지 링크. 인자가 없으면 기본 탭(진단). */
export function rebalancingUrl(options: RebalancingUrlOptions = {}): string {
  // 공백은 "+" 대신 %20 — decodeURIComponent 한 번으로 읽히게(이메일 링크·테스트 비교)
  const query = applyRebalancingParams(new URLSearchParams(), options)
    .toString()
    .replace(/\+/g, "%20");
  return query ? `/rebalancing?${query}` : "/rebalancing";
}
