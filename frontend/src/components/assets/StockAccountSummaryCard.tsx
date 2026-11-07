import { useMemo } from "react";
import { depositTotalKrw, fmtKrw } from "@/utils/format";
import type { AssetAccount } from "@/api/assets";
import type { AccountStats } from "./StockAccountCard";

interface Props {
  perAccountStats: { account: AssetAccount; stats: AccountStats }[];
  usdRate: number | null;
}

// 평가금액·평가손익은 자산 › 투자현황 요약 카드가 권위 표면이라 여기서는 계좌 합계성 값만 보여준다.
export default function StockAccountSummaryCard({ perAccountStats, usdRate }: Props) {
  const { totalDeposit, totalDividend, totalDepositKrw, rateMissing } = useMemo(() => {
    const deposit = perAccountStats.reduce((s, { stats }) => s + stats.deposit_total, 0);
    const dividend = perAccountStats.reduce((s, { stats }) => s + stats.dividend_total, 0);
    // 환율이 없으면 달러 예수금은 빼고 원화만 합친다 — 1:1로 더하면 $가 원으로 보였다(plans/116 C3)
    let depositKrw = 0;
    let missing = false;
    for (const { account } of perAccountStats) {
      const total = depositTotalKrw(account, usdRate);
      if (total == null) missing = true;
      depositKrw += total ?? account.deposit_krw ?? 0;
    }
    return {
      totalDeposit: deposit,
      totalDividend: dividend,
      totalDepositKrw: depositKrw,
      rateMissing: missing,
    };
  }, [perAccountStats, usdRate]);

  return (
    <div className="card">
      <h3 className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-3">증권계좌 합계</h3>
      <div className="grid grid-cols-3 gap-x-4 sm:gap-x-6 gap-y-3">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">누적 입금</p>
          <p className="text-sm font-semibold text-blue-600 dark:text-blue-400 mt-0.5">
            {fmtKrw(totalDeposit)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">누적 배당</p>
          <p className="text-sm font-semibold text-green-600 dark:text-green-400 mt-0.5">
            {fmtKrw(totalDividend)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">예수금</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">
            {fmtKrw(totalDepositKrw)}
          </p>
          {rateMissing && (
            <p className="text-xs text-gray-400 dark:text-gray-500">달러 제외 · 환율 조회 중</p>
          )}
        </div>
      </div>
    </div>
  );
}
