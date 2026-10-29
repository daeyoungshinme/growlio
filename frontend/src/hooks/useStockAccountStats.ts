import { useMemo } from "react";
import type { AssetAccount } from "@/api/assets";
import type { TransactionTotal } from "@/api/transactions";
import type { PortfolioOverview } from "@/types";
import type { AccountStats } from "@/components/assets/StockAccountCard";

export function useStockAccountStats(
  stockAccounts: AssetAccount[],
  overview: PortfolioOverview | undefined,
  txTotals: TransactionTotal[],
): { account: AssetAccount; stats: AccountStats }[] {
  return useMemo(() => {
    const portfolioAccMap = Object.fromEntries((overview?.accounts ?? []).map((a) => [a.id, a]));
    const txByAcc: Record<string, { deposit: number; dividend: number }> = {};
    for (const t of txTotals) {
      if (!t.account_id) continue;
      const acc = (txByAcc[t.account_id] ??= { deposit: 0, dividend: 0 });
      if (t.transaction_type === "DEPOSIT") acc.deposit += t.total_amount;
      if (t.transaction_type === "DIVIDEND") acc.dividend += t.total_amount;
    }
    return stockAccounts.map((account) => {
      const pa = portfolioAccMap[account.id];
      const tx = txByAcc[account.id] ?? { deposit: 0, dividend: 0 };
      return {
        account,
        stats: {
          amount_krw: pa?.amount_krw ?? 0,
          invested_krw: pa?.invested_krw ?? 0,
          unrealized_pnl: pa?.unrealized_pnl ?? 0,
          deposit_total: tx.deposit,
          dividend_total: tx.dividend,
        } as AccountStats,
      };
    });
  }, [stockAccounts, overview, txTotals]);
}
