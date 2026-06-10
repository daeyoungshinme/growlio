import { useState } from "react";
import { Pencil, Trash2, RefreshCw } from "lucide-react";
import type { AssetAccount } from "@/api/assets";
import { fmtKrw } from "@/utils/format";
import { useExchangeRateContext } from "@/context/ExchangeRateContext";

const BANK_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "입출금",
  DEPOSIT: "예·적금",
  CASH_OTHER: "현금/기타",
};

interface Props {
  account: AssetAccount;
  onDelete: (id: string) => void;
  onEditModal: (id: string) => void;
  onEditName: (id: string, name: string) => void;
  onSync: (id: string) => void;
  isDeleting: boolean;
  isSyncing: boolean;
}

export default function BankAccountCard({ account, onDelete, onEditModal, onEditName, onSync, isDeleting, isSyncing }: Props) {
  const { rate: usdRate } = useExchangeRateContext();
  const typeLabel = BANK_TYPE_LABELS[account.asset_type] ?? account.asset_type;
  const [editNameMode, setEditNameMode] = useState(false);
  const [editNameValue, setEditNameValue] = useState(account.name);

  const handleSaveName = () => {
    const trimmed = editNameValue.trim();
    if (trimmed) {
      onEditName(account.id, trimmed);
      setEditNameMode(false);
    }
  };

  const hasDepositFields = account.deposit_krw != null || account.deposit_usd != null;
  const displayTotal = hasDepositFields
    ? (account.deposit_krw ?? 0) + (account.deposit_usd && usdRate ? account.deposit_usd * usdRate : 0)
    : (account.manual_amount ?? 0);

  const showAmount = hasDepositFields ? displayTotal > 0 : account.manual_amount != null;

  return (
    <div className="card flex items-start justify-between gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {editNameMode ? (
            <>
              <input
                type="text"
                value={editNameValue}
                autoFocus
                onChange={(e) => setEditNameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") { setEditNameMode(false); setEditNameValue(account.name); }
                }}
                className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-0.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button onClick={handleSaveName} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
              <button onClick={() => { setEditNameMode(false); setEditNameValue(account.name); }} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
            </>
          ) : (
            <>
              <span className="text-sm font-semibold text-gray-900 dark:text-gray-50 truncate">{account.name}</span>
              <button
                onClick={() => { setEditNameValue(account.name); setEditNameMode(true); }}
                title="계좌명 수정"
                aria-label="계좌명 수정"
                className="p-2 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0">
                <Pencil size={16} />
              </button>
            </>
          )}
          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">{typeLabel}</span>
        </div>
        {account.institution && <p className="text-sm text-gray-500 dark:text-gray-400">{account.institution}</p>}
        {showAmount && (
          <div className="mt-1">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{fmtKrw(displayTotal)}</p>
            {hasDepositFields && account.deposit_usd != null && account.deposit_usd > 0 && (
              <p className="text-xs text-gray-400 dark:text-gray-500">
                ₩{(account.deposit_krw ?? 0).toLocaleString()} + ${account.deposit_usd.toLocaleString()}
                {usdRate ? ` (환율 ${usdRate.toLocaleString()}원/USD)` : ""}
              </p>
            )}
          </div>
        )}
        {account.notes && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{account.notes}</p>}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {account.data_source === "MANUAL" && (
          <button
            onClick={() => onEditModal(account.id)}
            title="금액 수정"
            aria-label="금액 수정"
            className="min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
            <Pencil size={15} />
          </button>
        )}
        {account.data_source === "OPEN_BANKING" && (
          <button
            onClick={() => onSync(account.id)}
            disabled={isSyncing}
            title="잔액 새로고침"
            aria-label="잔액 새로고침"
            className="min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-40">
            <RefreshCw size={15} className={isSyncing ? "animate-spin" : ""} />
          </button>
        )}
        <button onClick={() => onDelete(account.id)} disabled={isDeleting}
          className="min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 flex items-center justify-center p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50"
          title="계좌 삭제"
          aria-label="계좌 삭제">
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}
