import { useMemo } from "react";
import type { AssetAccount } from "@/api/assets";
import { BANK_TYPE_LABELS } from "@/constants";
import { fmtKrw } from "@/utils/format";
import { bankBalanceKrw } from "@/utils/accountSort";

interface Props {
  accounts: AssetAccount[];
  usdRate: number | null;
}

/** 은행계좌 탭 합계(plans/144 C3) — 증권·부동산 요약 카드와 같은 모양. 잔액 계산은 `BankAccountCard`와 같은 함수. */
export default function BankAccountSummaryCard({ accounts, usdRate }: Props) {
  const { total, byType, usdPending, excludedCount } = useMemo(() => {
    let sum = 0;
    let pending = false;
    const types = new Map<string, number>();
    // 합산 제외 계좌는 합계에서 뺀다 — 투자현황·홈 총자산과 같은 기준(plans/146 C2)
    const included = accounts.filter((a) => a.include_in_total !== false);
    for (const account of included) {
      const b = bankBalanceKrw(account, usdRate);
      sum += b.krw;
      pending ||= b.usdPending;
      types.set(account.asset_type, (types.get(account.asset_type) ?? 0) + b.krw);
    }
    return {
      total: sum,
      byType: [...types.entries()],
      usdPending: pending,
      excludedCount: accounts.length - included.length,
    };
  }, [accounts, usdRate]);

  return (
    <div className="card">
      <h3 className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-3">은행계좌 합계</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">총 잔액</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">
            {fmtKrw(total)}
          </p>
          {usdPending && (
            <p className="text-xs text-gray-400 dark:text-gray-500">달러 제외 · 환율 조회 중</p>
          )}
        </div>
        {/* 유형이 하나뿐이면 총 잔액과 같은 숫자라 소계를 두지 않는다 */}
        {byType.length > 1 &&
          byType.map(([type, amount]) => (
            <div key={type}>
              <p className="text-xs text-gray-400 dark:text-gray-500">
                {BANK_TYPE_LABELS[type] ?? type}
              </p>
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-300 mt-0.5">
                {fmtKrw(amount)}
              </p>
            </div>
          ))}
      </div>
      {excludedCount > 0 && (
        <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
          합산 제외 계좌 {excludedCount}개는 빠짐
        </p>
      )}
    </div>
  );
}
