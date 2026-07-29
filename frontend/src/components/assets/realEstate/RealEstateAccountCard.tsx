import { Pencil, Trash2 } from "lucide-react";
import type { AssetAccount } from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

interface CardProps {
  account: AssetAccount;
  onDelete: (id: string) => void;
  onEdit: (account: AssetAccount) => void;
  isDeleting: boolean;
}

export function RealEstateAccountCard({ account, onDelete, onEdit, isDeleting }: CardProps) {
  const re = account.real_estate_details;
  const marketValue = account.manual_amount ?? 0;
  const mortgage = re?.mortgage_balance_krw ?? 0;
  const equity = marketValue - mortgage;
  const purchasePrice = re?.purchase_price_krw ?? 0;
  const appreciation = purchasePrice > 0 ? marketValue - purchasePrice : null;

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50 truncate">
              {account.name}
            </h3>
            {re?.property_type && (
              <span className="px-2 py-0.5 bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-300 text-xs rounded-full shrink-0">
                {re.property_type}
              </span>
            )}
            {!account.include_in_total && (
              <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">
                자산 제외
              </span>
            )}
          </div>
          {re?.address && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">{re.address}</p>
          )}
          {re?.purchase_date && (
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
              매입일: {re.purchase_date}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onEdit(account)}
            title="수정"
            aria-label="수정"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors`}
          >
            <Pencil size={15} />
          </button>
          <button
            onClick={() => onDelete(account.id)}
            disabled={isDeleting}
            title="삭제"
            aria-label="삭제"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50`}
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>
      <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">현재 시세</p>
          <p className="text-xs font-semibold text-gray-900 dark:text-gray-50 mt-0.5">
            {fmtKrw(marketValue)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">담보대출</p>
          <p className="text-xs font-semibold text-blue-500 mt-0.5">
            {mortgage > 0 ? `−${fmtKrw(mortgage)}` : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-400 dark:text-gray-500">순자산</p>
          <p className={`text-xs font-semibold mt-0.5 ${pnlColor(equity)}`}>{fmtKrw(equity)}</p>
        </div>
        {appreciation !== null && (
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">매입차익</p>
            <p className={`text-xs font-semibold mt-0.5 ${pnlColor(appreciation)}`}>
              {appreciation >= 0 ? "+" : ""}
              {fmtKrw(appreciation)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
