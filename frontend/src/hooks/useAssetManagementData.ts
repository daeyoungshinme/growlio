import { useQuery } from "@tanstack/react-query";
import { fetchAccounts, type AssetAccount } from "@/api/assets";
import { fetchPortfolioOverview } from "@/api/portfolios";
import { fetchTransactions } from "@/api/transactions";
import { useExchangeRate } from "./useExchangeRate";
import { QUERY_KEYS } from "@/constants/queryKeys";
import type { ASSET_MANAGEMENT_TABS } from "@/constants/tabs";

type Tab = (typeof ASSET_MANAGEMENT_TABS)[number];

export function useAssetManagementData(tab: Tab) {
  const isStockTab = tab === "증권계좌";

  const { data: accounts = [], isLoading } = useQuery({
    queryKey: QUERY_KEYS.accounts,
    queryFn: fetchAccounts,
  });

  const { data: overview } = useQuery({
    queryKey: QUERY_KEYS.portfolioOverview,
    queryFn: fetchPortfolioOverview,
    enabled: isStockTab,
  });

  const { data: allTx = [] } = useQuery({
    queryKey: QUERY_KEYS.transactionsAll,
    queryFn: () => fetchTransactions(),
    enabled: isStockTab,
  });

  const usdRate = useExchangeRate();

  return { accounts: accounts as AssetAccount[], isLoading, overview, allTx, usdRate };
}
