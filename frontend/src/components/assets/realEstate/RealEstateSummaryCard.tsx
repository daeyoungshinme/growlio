import type { AssetAccount } from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";

interface SummaryProps {
  accounts: AssetAccount[];
}

export function RealEstateSummaryCard({ accounts }: SummaryProps) {
  const totalMarketValue = accounts.reduce((s, a) => s + (a.manual_amount ?? 0), 0);
  const totalMortgage = accounts.reduce(
    (s, a) => s + (a.real_estate_details?.mortgage_balance_krw ?? 0),
    0,
  );
  const totalEquity = totalMarketValue - totalMortgage;
  const totalPurchasePrice = accounts.reduce(
    (s, a) => s + (a.real_estate_details?.purchase_price_krw ?? 0),
    0,
  );
  const totalAppreciation = totalPurchasePrice > 0 ? totalMarketValue - totalPurchasePrice : null;

  return (
    <div className="card">
      <h3 className="text-xs text-gray-400 dark:text-gray-500 font-medium mb-3">
        부동산 전체 요약
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">시세 합계</p>
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-50 mt-0.5">
            {fmtKrw(totalMarketValue)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">담보대출 합계</p>
          <p className="text-sm font-semibold text-blue-500 mt-0.5">
            {totalMortgage > 0 ? `−${fmtKrw(totalMortgage)}` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">순자산</p>
          <p className={`text-sm font-semibold mt-0.5 ${pnlColor(totalEquity)}`}>
            {fmtKrw(totalEquity)}
          </p>
        </div>
        {totalAppreciation !== null && (
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">매입차익 합계</p>
            <p className={`text-sm font-semibold mt-0.5 ${pnlColor(totalAppreciation)}`}>
              {totalAppreciation >= 0 ? "+" : ""}
              {fmtKrw(totalAppreciation)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
