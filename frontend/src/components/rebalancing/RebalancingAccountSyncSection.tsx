import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, Check, AlertCircle } from "lucide-react";
import type { AssetAccount } from "@/api/assets";
import { syncAccount } from "@/api/assets";
import { invalidateSyncData } from "@/utils/queryInvalidation";

const SYNCABLE_SOURCES = ["KIS_API", "KIWOOM_API"];

const SOURCE_LABEL: Record<string, string> = {
  KIS_API: "KIS",
  KIWOOM_API: "키움",
};

type SyncResult = "idle" | "syncing" | "done" | "error";

interface Props {
  accounts: AssetAccount[];
  onReanalyze: () => void;
}

export function RebalancingAccountSyncSection({ accounts, onReanalyze }: Props) {
  const queryClient = useQueryClient();
  const syncableAccounts = accounts.filter((a) => SYNCABLE_SOURCES.includes(a.data_source));

  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(syncableAccounts.map((a) => a.id)),
  );
  const [syncResult, setSyncResult] = useState<SyncResult>("idle");

  if (syncableAccounts.length === 0) return null;

  const isAllSelected = syncableAccounts.every((a) => selectedIds.has(a.id));

  function toggleAll() {
    setSelectedIds(isAllSelected ? new Set() : new Set(syncableAccounts.map((a) => a.id)));
  }

  function toggleAccount(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSync() {
    if (selectedIds.size === 0) return;
    setSyncResult("syncing");
    const ids = Array.from(selectedIds);
    const settled = await Promise.allSettled(ids.map((id) => syncAccount(id)));
    const allOk = settled.every((s) => s.status === "fulfilled");
    await invalidateSyncData(queryClient);
    setSyncResult(allOk ? "done" : "error");
  }

  function handleReanalyze() {
    setSyncResult("idle");
    onReanalyze();
  }

  const isSyncing = syncResult === "syncing";

  return (
    <div className="border-t border-gray-100 dark:border-gray-800 pt-4 mt-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          계좌 데이터 갱신
        </span>
        <label className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-500 dark:text-gray-400">
          <input
            type="checkbox"
            checked={isAllSelected}
            onChange={toggleAll}
            disabled={isSyncing}
            className="rounded text-blue-600"
          />
          전체 선택
        </label>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {syncableAccounts.map((account) => (
          <label
            key={account.id}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs cursor-pointer transition-colors ${
              selectedIds.has(account.id)
                ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300"
                : "border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-500 dark:text-gray-400"
            } ${isSyncing ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            <input
              type="checkbox"
              checked={selectedIds.has(account.id)}
              onChange={() => toggleAccount(account.id)}
              disabled={isSyncing}
              className="rounded text-blue-600"
            />
            <span className="font-medium truncate max-w-[120px]">{account.name}</span>
            <span className="shrink-0 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 px-1.5 py-0.5 rounded text-[10px]">
              {SOURCE_LABEL[account.data_source] ?? account.data_source}
            </span>
          </label>
        ))}
      </div>

      <div className="flex items-center justify-end gap-2">
        {syncResult === "done" && (
          <>
            <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
              <Check size={12} />
              동기화 완료
            </span>
            <button
              onClick={handleReanalyze}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <RefreshCw size={12} />
              재분석
            </button>
          </>
        )}
        {syncResult === "error" && (
          <>
            <span className="flex items-center gap-1 text-xs text-yellow-600 dark:text-yellow-400">
              <AlertCircle size={12} />
              일부 동기화 실패
            </span>
            <button
              onClick={() => void handleSync()}
              className="px-3 py-1.5 text-xs bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
            >
              재시도
            </button>
          </>
        )}
        {(syncResult === "idle" || syncResult === "syncing") && (
          <button
            onClick={() => void handleSync()}
            disabled={isSyncing || selectedIds.size === 0}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 disabled:opacity-40 transition-colors"
          >
            {isSyncing ? (
              <>
                <Loader2 size={12} className="animate-spin" />
                동기화 중...
              </>
            ) : (
              <>
                <RefreshCw size={12} />
                선택 계좌 동기화
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
