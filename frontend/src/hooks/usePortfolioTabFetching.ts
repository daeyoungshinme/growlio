import { useIsFetching } from "@tanstack/react-query";

const PORTFOLIO_TAB_PREFIXES = [
  "portfolios",
  "accounts",
  "rebalancing-alerts",
  "factor-analysis",
  "efficient-frontier",
  "rebalancing-strategy",
];

export function usePortfolioTabFetching(): boolean {
  const count = useIsFetching({
    predicate: (query) => {
      const key = query.queryKey as string[];
      return PORTFOLIO_TAB_PREFIXES.some((p) => key[0] === p);
    },
  });
  return count > 0;
}
