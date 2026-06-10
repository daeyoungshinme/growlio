import { useMemo } from "react";
import { fmtKrw, fmtPct } from "@/utils/format";
import type { AssetAccount } from "@/api/assets";
import type { PortfolioOverview } from "@/types";

interface Transaction {
  transaction_type: string;
  amount: number;
  account_id: string | null;
}

interface Props {
  stockAccounts: AssetAccount[];
  overview: PortfolioOverview | undefined;
  allTx: Transaction[];
  usdRate: number | null;
}

export default function StockAccountSummaryCard({ stockAccounts, overview, allTx, usdRate }: Props) {
  const { totalDeposit, totalDividend, totalDepositKrw, pnl, ret } = useMemo(() => {
    const deposit = allTx.filter((t) => t.transaction_type === "DEPOSIT").reduce((s, t) => s + t.amount, 0);
    const dividend = allTx.filter((t) => t.transaction_type === "DIVIDEND").reduce((s, t) => s + t.amount, 0);
    const depositKrw = stockAccounts.reduce(
      (s, a) => s + (a.deposit_krw ?? 0) + (a.deposit_usd ?? 0) * (usdRate ?? 1),
      0
    );
    return {
      totalDeposit: deposit,
      totalDividend: dividend,
      totalDepositKrw: depositKrw,
      pnl: overview?.unrealized_pnl_krw ?? 0,
      ret: overview?.stock_return_pct ?? 0,
    };
  }, [stockAccounts, overview, allTx, usdRate]);

  const pnlColor = pnl >= 0 ? "text-red-500" : "text-blue-500";

  return (
    <div className="card">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-3">증권계좌 전체 요약</p>
      <div className="grid grid-cols-3 gap-x-6 gap-y-3">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">{fmtKrw(overview?.total_stock_krw ?? 0)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">평가손익</p>
          <p className={`text-sm font-semibold mt-0.5 ${pnlColor}`}>
            {pnl >= 0 ? "+" : ""}{fmtKrw(pnl)}({fmtPct(ret)})
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">예수금</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">{fmtKrw(totalDepositKrw)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">누적 입금</p>
          <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">{fmtKrw(totalDeposit)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">누적 배당</p>
          <p className="text-sm font-semibold text-green-600 dark:text-green-400 mt-0.5">{fmtKrw(totalDividend)}</p>
        </div>
      </div>
    </div>
  );
}
