import { useMemo } from "react";
import { depositTotalKrw, fmtKrw, fmtPct, fmtSigned } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { sumDepositReturn } from "@/utils/accountReturn";
import InfoTip from "@/components/common/InfoTip";
import type { AssetAccount } from "@/api/assets";
import { DEPOSIT_RETURN_TIP, type AccountStats, type AccountStatsStatus } from "./StockAccountCard";

interface Props {
  perAccountStats: { account: AssetAccount; stats: AccountStats }[];
  usdRate: number | null;
  /** 계좌별 평가액(overview) 조회 상태 — ready가 아니면 평가액이 0으로 채워져 있어 입금 대비 수익을 내지 않는다 */
  statsStatus: AccountStatsStatus;
}

// 평가금액·평가손익은 자산 › 투자현황 요약 카드가 권위 표면이라 여기서는 계좌 합계성 값만 보여준다.
export default function StockAccountSummaryCard({ perAccountStats, usdRate, statsStatus }: Props) {
  const { totalDeposit, totalDividend, totalDepositKrw, rateMissing, vsDeposit, included } =
    useMemo(() => {
      // 합산 제외 계좌는 합계에서 뺀다 — 투자현황·홈 총자산과 같은 기준(plans/146 C2)
      const included = perAccountStats.filter(({ account }) => account.include_in_total !== false);
      const deposit = included.reduce((s, { stats }) => s + stats.deposit_total, 0);
      const dividend = included.reduce((s, { stats }) => s + stats.dividend_total, 0);
      // 환율이 없으면 달러 예수금은 빼고 원화만 합친다 — 1:1로 더하면 $가 원으로 보였다(plans/116 C3)
      let depositKrw = 0;
      let missing = false;
      for (const { account } of included) {
        const total = depositTotalKrw(account, usdRate);
        if (total == null) missing = true;
        depositKrw += total ?? account.deposit_krw ?? 0;
      }
      return {
        totalDeposit: deposit,
        totalDividend: dividend,
        totalDepositKrw: depositKrw,
        rateMissing: missing,
        included,
        // 평가액을 아직 못 받았거나 실패하면 0으로 채워져 "−100%"가 된다(plans/146 C1)
        vsDeposit:
          statsStatus !== "ready"
            ? null
            : sumDepositReturn(
                included.map(({ stats }) => ({
                  amountKrw: stats.amount_krw,
                  depositTotal: stats.deposit_total,
                  withdrawalTotal: stats.withdrawal_total ?? 0,
                })),
              ),
      };
    }, [perAccountStats, usdRate, statsStatus]);
  const excludedCount = perAccountStats.length - included.length;

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
      {vsDeposit && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between gap-2">
          <p className="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500">
            입금 대비 수익
            {vsDeposit.accountCount < included.length &&
              ` (입금 기록 있는 ${vsDeposit.accountCount}개 계좌)`}
            <InfoTip label="입금 대비 수익 설명" content={DEPOSIT_RETURN_TIP} />
          </p>
          <p className={`text-sm font-semibold tabular-nums ${pnlColor(vsDeposit.gain)}`}>
            {fmtSigned(vsDeposit.gain, fmtKrw)} ({fmtPct(vsDeposit.pct)})
          </p>
        </div>
      )}
      {excludedCount > 0 && (
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
          합산 제외 계좌 {excludedCount}개는 빠짐
        </p>
      )}
    </div>
  );
}
