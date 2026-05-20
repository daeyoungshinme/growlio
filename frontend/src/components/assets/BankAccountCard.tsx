import { useState } from "react";
import { Pencil, Trash2, RefreshCw } from "lucide-react";
import type { AssetAccount } from "../../api/assets";
import { fmtKrw } from "../../utils/format";

const BANK_TYPE_LABELS: Record<string, string> = {
  BANK_ACCOUNT: "입출금",
  DEPOSIT: "예·적금",
  CASH_OTHER: "현금/기타",
};

interface Props {
  account: AssetAccount;
  onDelete: (id: string) => void;
  onEditAmount: (id: string, amount: number) => void;
  onEditName: (id: string, name: string) => void;
  onSync: (id: string) => void;
  isDeleting: boolean;
  isSyncing: boolean;
}

export default function BankAccountCard({ account, onDelete, onEditAmount, onEditName, onSync, isDeleting, isSyncing }: Props) {
  const typeLabel = BANK_TYPE_LABELS[account.asset_type] ?? account.asset_type;
  const [editMode, setEditMode] = useState(false);
  const [editValue, setEditValue] = useState(String(account.manual_amount ?? 0));
  const [editNameMode, setEditNameMode] = useState(false);
  const [editNameValue, setEditNameValue] = useState(account.name);

  const handleSaveName = () => {
    const trimmed = editNameValue.trim();
    if (trimmed) {
      onEditName(account.id, trimmed);
      setEditNameMode(false);
    }
  };

  const handleSave = () => {
    const amount = Number(editValue);
    if (!isNaN(amount) && amount >= 0) {
      onEditAmount(account.id, amount);
      setEditMode(false);
    }
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 flex items-start justify-between gap-4">
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
                className="p-0.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0">
                <Pencil size={10} />
              </button>
            </>
          )}
          <span className="px-2 py-0.5 bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-xs rounded-full shrink-0">{typeLabel}</span>
        </div>
        {account.institution && <p className="text-sm text-gray-500 dark:text-gray-400">{account.institution}</p>}
        {editMode ? (
          <div className="flex items-center gap-2 mt-2">
            <input
              type="number"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-1 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoFocus
              onKeyDown={(e) => { if (e.key === "Enter") handleSave(); if (e.key === "Escape") setEditMode(false); }}
            />
            <button onClick={handleSave} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
            <button onClick={() => setEditMode(false)} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
          </div>
        ) : (
          account.manual_amount != null && (
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mt-1">{fmtKrw(account.manual_amount)}</p>
          )
        )}
        {account.notes && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{account.notes}</p>}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {account.data_source === "MANUAL" && (
          <button
            onClick={() => { setEditValue(String(account.manual_amount ?? 0)); setEditMode(true); }}
            title="금액 수정"
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors">
            <Pencil size={15} />
          </button>
        )}
        {account.data_source === "OPEN_BANKING" && (
          <button
            onClick={() => onSync(account.id)}
            disabled={isSyncing}
            title="잔액 새로고침"
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950 rounded-lg transition-colors disabled:opacity-40">
            <RefreshCw size={15} className={isSyncing ? "animate-spin" : ""} />
          </button>
        )}
        <button onClick={() => onDelete(account.id)} disabled={isDeleting}
          className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors disabled:opacity-50"
          title="계좌 삭제">
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  );
}
