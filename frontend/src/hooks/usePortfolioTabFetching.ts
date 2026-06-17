import { useIsFetching } from "@tanstack/react-query";

const MAIN_PAGE_PREFIXES = [
  // 포트폴리오 탭
  "portfolios",
  "accounts",
  "rebalancing-alerts",
  "factor-analysis",
  "efficient-frontier",
  "rebalancing-strategy",
  // 대시보드 탭
  "dashboard",
  "portfolio-overview",
  "dca-analysis",
  "allocation-history",
  "dart-disclosures",
  // 포트폴리오 탭 배당 섹션
  "dividend-by-ticker",
  "dividend-summary",
  "dividend-positions",
];

export function useMainPageFetching(): boolean {
  const count = useIsFetching({
    predicate: (query) => {
      const key = query.queryKey as string[];
      return MAIN_PAGE_PREFIXES.some((p) => key[0] === p);
    },
  });
  return count > 0;
}
