import type { QueryClient } from "@tanstack/react-query";
import {
  accountsQuery,
  actionItemsQuery,
  challengesQuery,
  dashboardQuery,
  dcaAnalysisQuery,
  exchangeRateQuery,
  portfolioOverviewLiteQuery,
} from "@/api/queryOptions";

/**
 * 대시보드 첫 화면 데이터를 백그라운드로 미리 가져온다 — 앱 부팅(인증 확인 후)과 로그인 직후가 같은 목록을 쓴다.
 * 두 곳에 따로 적혀 있을 땐 로그인 쪽에만 settings가 빠져 있었다.
 * 지금 할 일·챌린지는 홈 두 번째 카드라 lazy 청크 로드를 기다리지 않게 함께 시작한다. settings는 홈에서 쓰지 않아 뺐다
 * (plans/125 C3). 부팅에선 저장된 토큰이 유효하면 persist 복원 직후(main.tsx) — Supabase SDK 로드 전에 — 부른다.
 */
export function prefetchDashboardData(qc: QueryClient): void {
  void qc.prefetchQuery(dashboardQuery);
  void qc.prefetchQuery(accountsQuery);
  void qc.prefetchQuery(portfolioOverviewLiteQuery);
  void qc.prefetchQuery(dcaAnalysisQuery);
  void qc.prefetchQuery(exchangeRateQuery);
  void qc.prefetchQuery(actionItemsQuery);
  void qc.prefetchQuery(challengesQuery);
}
