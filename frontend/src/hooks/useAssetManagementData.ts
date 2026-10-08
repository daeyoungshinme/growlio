import { useQuery } from "@tanstack/react-query";
import { fetchAccounts, type AssetAccount } from "@/api/assets";
import { fetchPortfolioOverviewLite } from "@/api/portfolios";
import { fetchTransactions } from "@/api/transactions";
import { useExchangeRate } from "./useExchangeRate";
import { QUERY_KEYS } from "@/constants/queryKeys";
import type { ASSET_MANAGEMENT_TABS } from "@/constants/tabs";

type Tab = (typeof ASSET_MANAGEMENT_TABS)[number];

export function useAssetManagementData(tab: Tab) {
  const isStockTab = tab === "증권계좌";

  const {
    data: accounts = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });

  // 증권계좌 카드의 계좌별 평가 통계에만 쓰인다(전체 자산 구성 카드는 plans/50 M3에서 제거)
  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverviewLite,
    queryFn: fetchPortfolioOverviewLite,
    enabled: isStockTab,
  });

  const { data: allTx = [] } = useQuery({
    queryKey: QUERY_KEYS.transactionsAll,
    queryFn: () => fetchTransactions(),
    enabled: isStockTab,
  });

  const usdRate = useExchangeRate();

  return { accounts: accounts as AssetAccount[], isLoading, error, overview, allTx, usdRate };
}
