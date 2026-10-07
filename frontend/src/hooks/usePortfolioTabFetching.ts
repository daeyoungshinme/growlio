import { useIsFetching } from "@tanstack/react-query";
import { QUERY_KEYS } from "@/constants/queryKeys";

// 각 키의 첫 요소(프리픽스)만 비교한다 — 계좌 필터 등 하위 변형까지 함께 잡힌다.
const MAIN_PAGE_PREFIXES: readonly string[] = [
  // 포트폴리오 탭
  QUERY_KEYS.portfolios,
  QUERY_KEYS.accounts,
  QUERY_KEYS.rebalancingAlerts,
  QUERY_KEYS.rebalancingStrategyBase,
  // 대시보드 탭
  QUERY_KEYS.dashboard,
  QUERY_KEYS.portfolioOverviewBase,
  QUERY_KEYS.dcaAnalysis,
  QUERY_KEYS.allocationHistoryBase,
  // 포트폴리오 탭 배당 섹션
  QUERY_KEYS.dividendByTickerBase,
  QUERY_KEYS.dividendSummaryBase,
  QUERY_KEYS.dividendPositionsBase,
].map((key) => key[0]);

export function useMainPageFetching(): boolean {
  const count = useIsFetching({
    predicate: (query) => MAIN_PAGE_PREFIXES.includes(String(query.queryKey[0])),
  });
  return count > 0;
}
