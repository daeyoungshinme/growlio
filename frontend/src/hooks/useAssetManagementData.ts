import { useQuery } from "@tanstack/react-query";
import { type AssetAccount } from "@/api/assets";
import { fetchTransactionSummary } from "@/api/transactions";
import { useExchangeRate } from "./useExchangeRate";
import { QUERY_KEYS } from "@/constants/queryKeys";
import type { ASSET_MANAGEMENT_TABS } from "@/constants/tabs";
import { accountsQuery, portfolioOverviewLiteQuery } from "@/api/queryOptions";

type Tab = (typeof ASSET_MANAGEMENT_TABS)[number];

export function useAssetManagementData(tab: Tab) {
  const isStockTab = tab === "증권계좌";

  const {
    data: accounts = [],
    isLoading,
    error,
    refetch: refetchAccounts,
  } = useQuery(accountsQuery);

  // 증권계좌 카드의 계좌별 평가 통계에만 쓰인다(전체 자산 구성 카드는 plans/50 M3에서 제거)
  const { data: overview } = useQuery({
    ...portfolioOverviewLiteQuery,
    enabled: isStockTab,
  });

  // 계좌 카드의 입금·배당 누계 — 목록 첫 페이지(100건)를 더하면 오래된 기록이 빠져 서버에서 합산한다(plans/90 B2)
  const { data: txTotals = [] } = useQuery({
    queryKey: QUERY_KEYS.transactionSummary,
    queryFn: () => fetchTransactionSummary(),
    enabled: isStockTab,
  });

  const usdRate = useExchangeRate();

  return {
    accounts: accounts as AssetAccount[],
    isLoading,
    error,
    refetchAccounts,
    overview,
    txTotals,
    usdRate,
  };
}
