import type { QueryClient } from "@tanstack/react-query";
import {
  accountsQuery,
  actionItemsQuery,
  challengesQuery,
  dashboardQuery,
  exchangeRateQuery,
} from "@/api/queryOptions";

/**
 * 대시보드 첫 화면 데이터를 백그라운드로 미리 가져온다 — 앱 부팅(인증 확인 후)과 로그인 직후가 같은 목록을 쓴다.
 * 두 곳에 따로 적혀 있을 땐 로그인 쪽에만 settings가 빠져 있었다.
 * 지금 할 일·챌린지는 홈 두 번째 카드라 lazy 청크 로드를 기다리지 않게 함께 시작한다. settings는 홈에서 쓰지 않아 뺐다
 * (plans/125 C3). 주식 평가손익·목표 달성 예상월은 대시보드 응답에 함께 와서 lite overview·적립 분석은 받지 않는다
 * (plans/151 B1). 부팅에선 저장된 토큰이 유효하면 persist 복원 직후(main.tsx) — Supabase SDK 로드 전에 — 부른다.
 */
export function prefetchDashboardData(qc: QueryClient): void {
  void qc.prefetchQuery(dashboardQuery);
  void qc.prefetchQuery(accountsQuery);
  void qc.prefetchQuery(exchangeRateQuery);
  void qc.prefetchQuery(actionItemsQuery);
  void qc.prefetchQuery(challengesQuery);
}

// App.tsx 라우트 중 홈이 아닌 화면 — 여기 없는 경로("/", "/dashboard", 모르는 경로)는 홈으로 간다
const NON_HOME_PATH_PREFIXES = [
  "/assets",
  "/rebalancing",
  "/invest-plan",
  "/settings",
  "/login",
  "/register",
  "/forgot-password",
  "/reset-password",
  "/auth/",
];

/**
 * 부팅 진입 경로가 홈인지 — 홈일 때만 홈 데이터를 미리 받는다. 푸시·메일 딥링크로 리밸런싱·계획 화면에 바로
 * 들어오면 홈의 무거운 요청(지금 할 일 등)이 그 화면 요청과 콜드 서버를 두고 경쟁했다(plans/151 B3).
 */
export function isHomeEntryPath(pathname: string): boolean {
  return !NON_HOME_PATH_PREFIXES.some((prefix) => pathname.startsWith(prefix));
}
