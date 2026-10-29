import type { QueryClient } from "@tanstack/react-query";
import { fetchDashboard } from "@/api/dashboard";
import { fetchExchangeRate } from "@/api/assets";
import { fetchDCAAnalysis } from "@/api/invest";
import { accountsQuery, portfolioOverviewLiteQuery, settingsQuery } from "@/api/queryOptions";
import { QUERY_KEYS } from "@/constants/queryKeys";

/**
 * 대시보드 첫 화면 데이터를 백그라운드로 미리 가져온다 — 앱 부팅(인증 확인 후)과 로그인 직후가 같은 목록을 쓴다.
 * 두 곳에 따로 적혀 있을 땐 로그인 쪽에만 settings가 빠져 있었다.
 */
export function prefetchDashboardData(qc: QueryClient): void {
  void qc.prefetchQuery({ queryKey: QUERY_KEYS.dashboard, queryFn: () => fetchDashboard() });
  void qc.prefetchQuery(accountsQuery);
  void qc.prefetchQuery(portfolioOverviewLiteQuery);
  void qc.prefetchQuery({ queryKey: QUERY_KEYS.dcaAnalysis, queryFn: () => fetchDCAAnalysis() });
  void qc.prefetchQuery({ queryKey: QUERY_KEYS.exchangeRate, queryFn: () => fetchExchangeRate() });
  void qc.prefetchQuery(settingsQuery);
}
