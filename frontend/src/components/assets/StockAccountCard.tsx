import { BarChart2, Loader2, Pencil, Receipt, RefreshCw, Settings, Trash2 } from "lucide-react";
import {
  type AssetAccount,
  ACCOUNT_TAX_TYPE_LABELS,
  INVESTMENT_HORIZON_LABELS,
} from "@/api/assets";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { useHaptic } from "@/hooks/useHaptic";
import { convertUsdToKrw, fmtKrw, fmtPct } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { STOCK_TYPE_LABELS } from "@/constants";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";
import EditableNameField from "@/components/common/EditableNameField";

export interface AccountStats {
  amount_krw: number;
  invested_krw: number;
  unrealized_pnl: number;
  deposit_total: number;
  dividend_total: number;
}

interface Props {
  account: AssetAccount;
  stats?: AccountStats;
  onDelete: (id: string) => void;
  onManagePositions: (account: { id: string; name: string; dataSource: string }) => void;
  onTransactions: (account: { id: string; name: string }) => void;
  onEdit: (account: AssetAccount) => void;
  onEditName: (id: string, name: string) => void;
  onSync: (id: string) => void;
  isSyncing: boolean;
  isDeleting: boolean;
}

export default function StockAccountCard({
  account,
  stats,
  onDelete,
  onManagePositions,
  onTransactions,
  onEdit,
  onEditName,
  onSync,
  isSyncing,
  isDeleting,
}: Props) {
  const typeLabel = STOCK_TYPE_LABELS[account.asset_type] ?? account.asset_type;
  const accountNo = account.kis_account_no ?? account.kiwoom_account_no ?? null;
  const hasStats =
    stats && (stats.amount_krw > 0 || stats.deposit_total > 0 || stats.dividend_total > 0);
  const pnl = stats?.unrealized_pnl ?? 0;
  const ret = stats?.invested_krw ? (pnl / stats.invested_krw) * 100 : 0;
  const usdRate = useExchangeRate();
  const { impact } = useHaptic();

  return (
    <div className="card">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* 줄1: 계좌명 + 편집버튼 */}
          <EditableNameField
            name={account.name}
            onSave={(name) => onEditName(account.id, name)}
            className="min-w-0"
            textClassName="text-base font-semibold text-gray-900 dark:text-gray-50 truncate"
          />
          {/* 줄2: 기관명·계좌번호 (truncate, 항상 1줄) */}
          {(account.institution || accountNo) && (
            <div className="mt-1 min-w-0">
              <span className="text-xs text-gray-400 dark:text-gray-500 truncate block">
                {[account.institution, accountNo].filter(Boolean).join(" · ")}
              </span>
            </div>
          )}
          {/* 줄3: 배지 (넘치면 다음 줄로 — 현재 라벨 조합 기준 사실상 1줄) */}
          <div className="flex flex-wrap items-center gap-1.5 gap-y-1 mt-1 min-w-0">
            <span className="px-1.5 py-px bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">
              {typeLabel}
            </span>
            {account.tax_type && account.tax_type !== "GENERAL" && (
              <span className="px-1.5 py-px border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-400 text-xs rounded-full shrink-0">
                {ACCOUNT_TAX_TYPE_LABELS[account.tax_type]}
              </span>
            )}
            {account.investment_horizon && (
              <span className="px-1.5 py-px border border-teal-300 dark:border-teal-700 text-teal-600 dark:text-teal-400 text-xs rounded-full shrink-0">
                {INVESTMENT_HORIZON_LABELS[account.investment_horizon]}
              </span>
            )}
            {account.has_own_kis_credentials && (
              <span className="px-1.5 py-px border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 text-xs rounded-full shrink-0">
                API 키
              </span>
            )}
            {account.has_own_kiwoom_credentials && (
              <span className="px-1.5 py-px border border-amber-300 dark:border-amber-700 text-amber-600 dark:text-amber-400 text-xs rounded-full shrink-0">
                키움 API 키
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-wrap justify-end gap-1 shrink-0">
          <button
            onClick={() => onEdit(account)}
            title="계좌 수정"
            aria-label="계좌 수정"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-400 hover:text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-950 rounded-lg transition-colors`}
          >
            <Settings size={16} />
          </button>
          {(account.data_source === "KIS_API" || account.data_source === "KIWOOM_API") && (
            <button
              onClick={() => {
                impact("light");
                onSync(account.id);
              }}
              disabled={isSyncing}
              title={
                account.data_source === "KIWOOM_API" ? "키움 데이터 동기화" : "KIS 데이터 동기화"
              }
              aria-label={
                account.data_source === "KIWOOM_API" ? "키움 데이터 동기화" : "KIS 데이터 동기화"
              }
              className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-50`}
            >
              {isSyncing ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            </button>
          )}
          <button
            onClick={() =>
              onManagePositions({
                id: account.id,
                name: account.name,
                dataSource: account.data_source,
              })
            }
            title="종목 관리"
            aria-label="종목 관리"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-400 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950 rounded-lg transition-colors`}
          >
            <BarChart2 size={16} />
          </button>
          <button
            onClick={() => onTransactions({ id: account.id, name: account.name })}
            title="입출금 내역"
            aria-label="입출금 내역"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 dark:hover:bg-green-950 rounded-lg transition-colors`}
          >
            <Receipt size={16} />
          </button>
          <button
            onClick={() => onDelete(account.id)}
            disabled={isDeleting}
            title="계좌 삭제"
            aria-label="계좌 삭제"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50`}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      {hasStats && (
        <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 grid grid-cols-3 gap-x-4 gap-y-2">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">평가금액</p>
            <p className="text-xs font-semibold text-gray-900 dark:text-gray-50 mt-0.5">
              {fmtKrw(stats!.amount_krw)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">평가손익</p>
            <p className={`text-xs font-semibold mt-0.5 ${pnlColor(pnl)}`}>
              {pnl >= 0 ? "+" : ""}
              {fmtKrw(pnl)}
            </p>
            <p className={`text-xs font-medium ${pnlColor(pnl)}`}>({fmtPct(ret)})</p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">누적 입금</p>
            <p className="text-xs font-semibold text-blue-600 dark:text-blue-400 mt-0.5">
              {fmtKrw(stats!.deposit_total)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">누적 배당</p>
            <p className="text-xs font-semibold text-green-600 dark:text-green-400 mt-0.5">
              {fmtKrw(stats!.dividend_total)}
            </p>
          </div>
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-500">예수금</p>
            <div className="flex items-start gap-1 mt-0.5">
              <div className="flex-1 min-w-0">
                {(() => {
                  const krw = account.deposit_krw ?? 0;
                  const usd = account.deposit_usd ?? 0;
                  const hasUsd = usd > 0;
                  const usdAsKrw = convertUsdToKrw(hasUsd ? usd : null, usdRate);
                  const total = krw + usdAsKrw;
                  return (
                    <>
                      <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">
                        {fmtKrw(hasUsd && usdRate ? total : krw)}
                      </p>
                      {hasUsd && (
                        <p className="text-xs text-gray-400 dark:text-gray-500">
                          {usdRate
                            ? `${fmtKrw(krw)} + $${usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
                            : `$${usd.toLocaleString(undefined, { maximumFractionDigits: 2 })} (환율 조회 중)`}
                        </p>
                      )}
                    </>
                  );
                })()}
              </div>
              <button
                onClick={() => onEdit(account)}
                aria-label="예수금 수정"
                className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 dark:hover:text-blue-400 transition-colors shrink-0`}
              >
                <Pencil size={12} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
